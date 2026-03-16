use anyhow::{Context, Result};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tracing::{info, warn, error, debug};
use std::process::Stdio;
use tokio::process::Command;
use tokio::io::AsyncWriteExt;
use std::time::Duration;
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{Consumer, StreamConsumer};
use rdkafka::message::Message;
use rdkafka::producer::{FutureProducer, FutureRecord};
use rdkafka::util::Timeout;
use walkdir::WalkDir;
use common::{SendTaskParams, Part};

/// A discovered skill with its name and the path to its run.py script
#[derive(Debug, Clone)]
struct SkillEntry {
    name: String,
    script_path: PathBuf,
    description: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    info!("Starting Skill Server Lite (direct spawn, no opencode-exec)...");

    // Discover skills root directory
    let skills_root = find_skills_root()?;
    info!("Skills root: {:?}", skills_root);

    // Scan and index all available skills
    let skills = discover_skills(&skills_root)?;

    // Filter skills to current category if SKILLSCALE_CATEGORY is set
    let category = std::env::var("SKILLSCALE_CATEGORY").ok();
    let skills = if let Some(ref cat) = category {
        let filtered: Vec<SkillEntry> = skills.into_iter().filter(|s| {
            // Keep skill if its path contains /<category>/ segment
            let path_str = s.script_path.to_string_lossy();
            let pattern = format!("/{}/", cat);
            path_str.contains(&pattern)
        }).collect();
        info!("Filtered to category '{}': {} skills", cat, filtered.len());
        filtered
    } else {
        skills
    };

    info!("Discovered {} skills:", skills.len());
    for s in &skills {
        info!("  - {} -> {:?}", s.name, s.script_path);
    }

    // Detect sandbox mode (Phase 2: skilllite-sandbox)
    let sandbox_mode = detect_sandbox_mode();
    info!("Sandbox mode: {:?}", sandbox_mode);

    let broker_url = std::env::var("SKILLSCALE_BROKER_URL")
        .unwrap_or_else(|_| "localhost:9092".to_string());

    let group_id = std::env::var("SKILLSCALE_GROUP_ID")
        .unwrap_or_else(|_| format!("skill-server-{}", uuid::Uuid::new_v4()));
    let consumer: StreamConsumer = ClientConfig::new()
        .set("group.id", &group_id)
        .set("bootstrap.servers", &broker_url)
        .set("enable.partition.eof", "false")
        .set("session.timeout.ms", "6000")
        .set("enable.auto.commit", "true")
        .set("auto.offset.reset", "earliest")
        .create()
        .context("Consumer creation failed")?;

    let producer: FutureProducer = ClientConfig::new()
        .set("bootstrap.servers", &broker_url)
        .set("message.timeout.ms", "5000")
        .create()
        .context("Producer creation failed")?;

    let topic = std::env::var("SKILLSCALE_TOPIC")
        .unwrap_or_else(|_| "skill.request".to_string());
    consumer.subscribe(&[&topic])
        .context("Can't subscribe to topic")?;

    info!("Subscribed to '{}'. Waiting for messages...", topic);

    // Load AGENTS.md descriptions and enrich skill entries
    let skills = enrich_skills_from_agents_md(&skills_root, skills);

    // Build a name->entry lookup map
    let skill_map: HashMap<String, SkillEntry> = skills
        .into_iter()
        .map(|s| (s.name.clone(), s))
        .collect();

    loop {
        match consumer.recv().await {
            Err(e) => warn!("Kafka error: {}", e),
            Ok(m) => {
                let payload = match m.payload_view::<str>() {
                    None => "",
                    Some(Ok(s)) => s,
                    Some(Err(e)) => {
                        warn!("Error while deserializing message payload: {:?}", e);
                        ""
                    }
                };

                info!("Received message: {}", payload);
                if !payload.is_empty() {
                    // Extract reply metadata
                    let mut reply_to = None;
                    let mut request_id = None;

                    if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(payload) {
                        if let Some(meta) = json_val.get("metadata") {
                            reply_to = meta.get("reply_to").and_then(|v| v.as_str()).map(|s| s.to_string());
                            request_id = meta.get("request_id").and_then(|v| v.as_str()).map(|s| s.to_string());
                        }
                    }

                    // Parse skill name and input text
                    let (skill_name, skill_input) = match serde_json::from_str::<SendTaskParams>(payload) {
                        Ok(params) => {
                            let s = params.metadata.as_ref()
                                .and_then(|m| m.get("skill").cloned())
                                .unwrap_or_default();

                            let text = params.message.parts.iter()
                                .filter_map(|p| match p {
                                    Part::Text { text } => Some(text.as_str()),
                                })
                                .collect::<Vec<&str>>()
                                .join("\n");

                            (s, text)
                        }
                        Err(_) => {
                            match serde_json::from_str::<serde_json::Value>(payload) {
                                Ok(v) => {
                                    let s = v["skill"].as_str().unwrap_or("").to_string();
                                    let i = v["input"].as_str().unwrap_or(payload).to_string();
                                    (s, i)
                                }
                                Err(_) => (String::new(), payload.to_string()),
                            }
                        }
                    };

                    info!("Executing skill: '{}' with input len: {}", skill_name, skill_input.len());

                    // Resolve skill: direct match first, then LLM-based coarse routing
                    let resolved_skill = if skill_map.contains_key(&skill_name) {
                        Some(skill_name.clone())
                    } else if skill_name.is_empty() || !skill_map.values().any(|e| e.name == skill_name) {
                        // Coarse-grained: no exact skill match → ask LLM to pick best skill
                        info!("Coarse-grained routing: asking LLM to match input to best skill...");
                        match match_skill_by_llm(&skill_map, &skill_input).await {
                            Some(matched) => {
                                info!("LLM matched to skill: '{}'", matched);
                                Some(matched)
                            }
                            None => {
                                warn!("LLM could not match any skill for input.");
                                None
                            }
                        }
                    } else {
                        None
                    };

                    let execution_result = if let Some(ref resolved) = resolved_skill {
                        if let Some(entry) = skill_map.get(resolved) {
                            match execute_skill_direct(&entry.script_path, &skill_input, &sandbox_mode).await {
                                Ok(output) => {
                                    info!("Skill '{}' executed successfully.", resolved);
                                    Ok(output)
                                }
                                Err(e) => {
                                    error!("Skill '{}' execution failed: {:?}", resolved, e);
                                    Err(e.to_string())
                                }
                            }
                        } else {
                            Err(format!("Resolved skill '{}' not found in map", resolved))
                        }
                    } else {
                        error!("Cannot route skill '{}'. Available: {:?}", skill_name,
                            skill_map.keys().collect::<Vec<_>>());
                        Err(format!("Unknown skill '{}'. Available skills: {:?}",
                            skill_name, skill_map.keys().collect::<Vec<_>>()))
                    };

                    // Send Reply if reply_to and request_id exist
                    if let (Some(reply_topic), Some(req_id)) = (reply_to, request_id) {
                        let response_payload = match execution_result {
                            Ok(output) => serde_json::json!({
                                "result": output,
                                "status": "success",
                                "metadata": { "request_id": req_id }
                            }),
                            Err(err_msg) => serde_json::json!({
                                "error": err_msg,
                                "status": "error",
                                "metadata": { "request_id": req_id }
                            })
                        };

                        let payload_str = response_payload.to_string();
                        let record = FutureRecord::to(&reply_topic)
                            .key(&req_id)
                            .payload(&payload_str);

                        info!("Sending reply to {} (req: {})", reply_topic, req_id);
                        if let Err((e, _)) = producer.send(record, Timeout::After(Duration::from_secs(5))).await {
                            error!("Failed to send reply: {}", e);
                        }
                    } else {
                        warn!("No reply_to/request_id found in metadata, skipping reply.");
                    }
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Skill Discovery — scans skills/ tree for run.py scripts
// ---------------------------------------------------------------------------

/// Find the skills/ root directory by checking common relative paths
fn find_skills_root() -> Result<PathBuf> {
    let candidates = vec![
        PathBuf::from("./skills"),
        PathBuf::from("../skills"),
        PathBuf::from("../../skills"),
    ];

    for p in &candidates {
        if p.is_dir() {
            return Ok(p.canonicalize()?);
        }
    }

    // Fallback: SKILLSCALE_ROOT env var
    if let Ok(root) = std::env::var("SKILLSCALE_ROOT") {
        let p = Path::new(&root).join("skills");
        if p.is_dir() {
            return Ok(p);
        }
    }

    // Fallback: /skills (Docker container mount)
    let docker_path = PathBuf::from("/skills");
    if docker_path.is_dir() {
        return Ok(docker_path);
    }

    anyhow::bail!(
        "Cannot find skills/ directory. Checked: {:?}. Set SKILLSCALE_ROOT to the project root.",
        candidates
    );
}

/// Parse AGENTS.md files to extract skill descriptions and enrich SkillEntry objects.
fn enrich_skills_from_agents_md(skills_root: &Path, mut skills: Vec<SkillEntry>) -> Vec<SkillEntry> {
    // Find all AGENTS.md files
    for entry in WalkDir::new(skills_root)
        .max_depth(2)
        .follow_links(true)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if entry.file_name() == "AGENTS.md" {
            if let Ok(content) = std::fs::read_to_string(entry.path()) {
                // Parse <skill> blocks to extract name and description
                let mut current_name = String::new();
                let mut current_desc = String::new();
                let mut in_skill = false;
                let mut in_desc = false;

                for line in content.lines() {
                    let trimmed = line.trim();
                    if trimmed.starts_with("<skill>") {
                        in_skill = true;
                        current_name.clear();
                        current_desc.clear();
                    } else if trimmed.starts_with("</skill>") {
                        if in_skill && !current_name.is_empty() {
                            // Find and enrich the matching skill
                            for skill in skills.iter_mut() {
                                if skill.name == current_name && skill.description.is_empty() {
                                    skill.description = current_desc.trim().to_string();
                                    debug!("Enriched skill '{}' with description from AGENTS.md", skill.name);
                                }
                            }
                        }
                        in_skill = false;
                        in_desc = false;
                    } else if in_skill {
                        if trimmed.starts_with("<name>") && trimmed.ends_with("</name>") {
                            current_name = trimmed
                                .trim_start_matches("<name>")
                                .trim_end_matches("</name>")
                                .trim()
                                .to_string();
                        } else if trimmed.starts_with("<description>") {
                            in_desc = true;
                            let after = trimmed.trim_start_matches("<description>");
                            if after.ends_with("</description>") {
                                current_desc = after.trim_end_matches("</description>").trim().to_string();
                                in_desc = false;
                            } else {
                                current_desc = after.to_string();
                            }
                        } else if trimmed.starts_with("</description>") {
                            in_desc = false;
                        } else if in_desc {
                            if !current_desc.is_empty() {
                                current_desc.push(' ');
                            }
                            current_desc.push_str(trimmed);
                        }
                    }
                }
            }
        }
    }
    skills
}

/// Use LLM to pick the best skill for the given input text.
/// Calls the OpenAI-compatible chat completions API configured via env vars.
async fn match_skill_by_llm(
    skill_map: &HashMap<String, SkillEntry>,
    input: &str,
) -> Option<String> {
    if skill_map.is_empty() {
        return None;
    }

    // Build skill catalog for the prompt
    let mut catalog = String::new();
    let skill_names: Vec<&String> = skill_map.keys().collect();
    for (name, entry) in skill_map.iter() {
        catalog.push_str(&format!("- {}", name));
        if !entry.description.is_empty() {
            catalog.push_str(&format!(": {}", entry.description));
        }
        catalog.push('\n');
    }

    let api_base = std::env::var("OPENAI_API_BASE")
        .unwrap_or_else(|_| "https://api.openai.com/v1".to_string());
    let api_key = std::env::var("OPENAI_API_KEY").unwrap_or_default();
    let model = std::env::var("OPENAI_MODEL")
        .unwrap_or_else(|_| "gpt-4o".to_string());

    if api_key.is_empty() {
        warn!("OPENAI_API_KEY not set, falling back to first skill");
        return skill_map.keys().next().cloned();
    }

    // Truncate input to avoid excessive token usage (first 500 chars)
    let truncated_input: String = input.chars().take(500).collect();

    let system_prompt = format!(
        "You are a skill router. Given a user request, pick the single best matching skill from the list below.\n\
         Reply with ONLY the skill name, nothing else. No explanation, no quotes, no punctuation.\n\n\
         Available skills:\n{}",
        catalog
    );

    let url = format!("{}/chat/completions", api_base.trim_end_matches('/'));

    let body = serde_json::json!({
        "model": model,
        "messages": [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": truncated_input }
        ],
        "max_tokens": 32,
        "temperature": 0.0
    });

    let client = reqwest::Client::new();
    match client
        .post(&url)
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(&body)
        .timeout(Duration::from_secs(15))
        .send()
        .await
    {
        Ok(resp) => {
            if let Ok(json) = resp.json::<serde_json::Value>().await {
                if let Some(choice) = json["choices"].get(0) {
                    let content = choice["message"]["content"]
                        .as_str()
                        .unwrap_or("")
                        .trim()
                        .to_string();
                    info!("LLM routing response: '{}'", content);

                    // Validate LLM returned a known skill name
                    if skill_map.contains_key(&content) {
                        return Some(content);
                    }
                    // Try case-insensitive / partial match
                    let content_lower = content.to_lowercase();
                    for name in &skill_names {
                        if name.to_lowercase() == content_lower {
                            return Some((*name).clone());
                        }
                    }
                    warn!("LLM returned unknown skill '{}', falling back", content);
                }
            }
        }
        Err(e) => {
            error!("LLM routing request failed: {}", e);
        }
    }

    // Fallback to first available skill
    let first = skill_map.keys().next().cloned();
    info!("LLM routing failed, falling back to first skill: {:?}", first);
    first
}

/// Walk the skills directory tree to find all `scripts/run.py` files.
/// Directory structure: skills/<category>/.claude/skills/<skill-name>/scripts/run.py
fn discover_skills(skills_root: &Path) -> Result<Vec<SkillEntry>> {
    let mut entries = Vec::new();

    for entry in WalkDir::new(skills_root)
        .follow_links(true)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        let path = entry.path();

        // Match pattern: .../scripts/run.py
        if path.file_name().map(|f| f == "run.py").unwrap_or(false) {
            if let Some(scripts_dir) = path.parent() {
                if scripts_dir.file_name().map(|f| f == "scripts").unwrap_or(false) {
                    // Skill name = parent directory of scripts/
                    if let Some(skill_dir) = scripts_dir.parent() {
                        let skill_name = skill_dir
                            .file_name()
                            .map(|f| f.to_string_lossy().to_string())
                            .unwrap_or_default();

                        if !skill_name.is_empty() {
                            debug!("Found skill: {} at {:?}", skill_name, path);
                            entries.push(SkillEntry {
                                name: skill_name,
                                script_path: path.to_path_buf(),
                                description: String::new(),
                            });
                        }
                    }
                }
            }
        }
    }

    Ok(entries)
}

// ---------------------------------------------------------------------------
// Skill Execution — direct spawn (Phase 1: Rust → script, 2-layer only)
//                   with optional sandbox (Phase 2: skilllite-sandbox)
// ---------------------------------------------------------------------------

/// Sandbox mode determined at startup
#[derive(Debug, Clone)]
enum SandboxMode {
    /// No sandbox — direct spawn (Phase 1 default)
    None,
    /// SkillLite sandbox — OS-native isolation via skilllite-sandbox binary
    SkillLite(PathBuf),
}

/// Detect sandbox mode from environment and PATH
fn detect_sandbox_mode() -> SandboxMode {
    let sandbox_env = std::env::var("SKILLSCALE_SANDBOX").unwrap_or_default();

    if sandbox_env == "none" || sandbox_env == "off" {
        return SandboxMode::None;
    }

    // If explicitly set to "skilllite" or auto-detect
    if sandbox_env == "skilllite" || sandbox_env.is_empty() {
        // Check if skilllite-sandbox binary is on PATH
        if let Ok(output) = std::process::Command::new("which")
            .arg("skilllite-sandbox")
            .output()
        {
            if output.status.success() {
                let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !path.is_empty() {
                    return SandboxMode::SkillLite(PathBuf::from(path));
                }
            }
        }

        // Check common locations
        for candidate in &[
            "/usr/local/bin/skilllite-sandbox",
            "/usr/bin/skilllite-sandbox",
            "./skilllite-sandbox",
        ] {
            let p = Path::new(candidate);
            if p.exists() {
                return SandboxMode::SkillLite(p.to_path_buf());
            }
        }

        // If explicitly requested but not found, warn
        if sandbox_env == "skilllite" {
            warn!("SKILLSCALE_SANDBOX=skilllite but skilllite-sandbox binary not found. Falling back to direct spawn.");
        }
    }

    SandboxMode::None
}

/// Execute a skill script directly via its shebang or python3.
/// This replaces the old 4-layer chain: Rust → bash → Go → Python
///
/// With sandbox_mode=SkillLite, wraps execution in skilllite-sandbox for
/// OS-native isolation (Seatbelt on macOS, bwrap/seccomp on Linux).
async fn execute_skill_direct(
    script_path: &Path,
    input: &str,
    sandbox_mode: &SandboxMode,
) -> Result<String> {
    let timeout_secs: u64 = std::env::var("SKILLSCALE_TIMEOUT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(120);

    // Set working directory to the skill's root (parent of scripts/)
    let work_dir = script_path
        .parent()  // scripts/
        .and_then(|p| p.parent())  // skill-name/
        .unwrap_or_else(|| Path::new("."));

    let mut cmd = match sandbox_mode {
        SandboxMode::SkillLite(sandbox_bin) => {
            // Phase 2: skilllite-sandbox run <script>
            // skilllite-sandbox provides OS-native isolation:
            //   macOS: Seatbelt (sandbox-exec)
            //   Linux: bubblewrap + seccomp
            let mut c = Command::new(sandbox_bin);
            c.arg("run");
            // Allow read access to the skill directory
            c.arg("--allow-read").arg(work_dir);
            // Allow network for LLM API calls if needed
            if std::env::var("SKILLSCALE_SANDBOX_NETWORK").unwrap_or_default() != "deny" {
                c.arg("--allow-net");
            }

            if is_executable(script_path) {
                c.arg("--").arg(script_path);
            } else {
                let python = std::env::var("SKILLSCALE_PYTHON")
                    .unwrap_or_else(|_| "python3".to_string());
                c.arg("--").arg(&python).arg(script_path);
            }
            c
        }
        SandboxMode::None => {
            // Phase 1: direct spawn
            if is_executable(script_path) {
                Command::new(script_path)
            } else {
                let python = std::env::var("SKILLSCALE_PYTHON")
                    .unwrap_or_else(|_| "python3".to_string());
                let mut c = Command::new(python);
                c.arg(script_path);
                c
            }
        }
    };

    cmd.current_dir(work_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("SKILLSCALE_INTENT", input);

    let mut child = cmd.spawn()
        .with_context(|| format!("Failed to spawn skill at {:?}", script_path))?;

    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(input.as_bytes()).await
            .context("Failed to write to skill stdin")?;
    }

    // Apply timeout
    let output = tokio::time::timeout(
        Duration::from_secs(timeout_secs),
        child.wait_with_output(),
    )
    .await
    .map_err(|_| anyhow::anyhow!("Skill execution timed out after {}s", timeout_secs))?
    .context("Failed to wait for skill output")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("Skill execution failed (exit {}): {}",
            output.status.code().unwrap_or(-1), stderr);
    }

    Ok(String::from_utf8_lossy(&output.stdout).to_string())
}

/// Check if a file has executable permission (Unix)
fn is_executable(path: &Path) -> bool {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Ok(meta) = std::fs::metadata(path) {
            return meta.permissions().mode() & 0o111 != 0;
        }
    }
    false
}
