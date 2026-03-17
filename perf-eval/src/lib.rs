//! Shared helpers and mirrored types used by the SkillScale Lite perf-eval benchmarks.
//!
//! The types below intentionally mirror those in `skillscale-rs/common` so that
//! this project stays fully independent (its own `Cargo.toml`, no workspace
//! membership) while still producing realistic payloads.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

// ── Core message types (mirrors skillscale-rs/common/src/lib.rs) ─────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillRequest {
    pub skill: String,
    pub data: Value,
    pub context: SkillContext,
    pub metadata: HashMap<String, String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillContext {
    pub session_id: String,
    pub protocol: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SendTaskParams {
    pub id: String,
    pub session_id: Option<String>,
    pub message: Message,
    pub metadata: Option<HashMap<String, String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub parts: Vec<Part>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "lowercase")]
pub enum Part {
    Text { text: String },
}

// ── Skill-discovery helpers (mirrors skillscale-rs/gateway/src/skill_discovery.rs) ──

/// Parse all `<skill> … </skill>` blocks from AGENTS.md content.
pub fn parse_agents_md(category: &str, content: &str) -> Vec<SkillDef> {
    let mut skills = Vec::new();
    for chunk in content.split("<skill>").skip(1) {
        if let Some(end_idx) = chunk.find("</skill>") {
            let block = &chunk[..end_idx];
            if let (Some(name), Some(desc)) = (extract_tag(block, "name"), extract_tag(block, "description")) {
                skills.push(SkillDef {
                    category: category.to_string(),
                    name: name.trim().to_string(),
                    description: desc.trim().to_string(),
                });
            }
        }
    }
    skills
}

/// Extract the inner text of `<tag_name>…</tag_name>` from a string slice.
pub fn extract_tag(content: &str, tag_name: &str) -> Option<String> {
    let open = format!("<{}>", tag_name);
    let close = format!("</{}>", tag_name);
    let start = content.find(&open)?;
    let end = content.find(&close)?;
    if start + open.len() < end {
        Some(content[start + open.len()..end].to_string())
    } else {
        None
    }
}

/// A discovered skill definition.
#[derive(Debug, Clone)]
pub struct SkillDef {
    pub category: String,
    pub name: String,
    pub description: String,
}

// ── Fixture builders ─────────────────────────────────────────────────────────

/// Build a realistic `SkillRequest` fixture for serialisation benchmarks.
pub fn make_skill_request() -> SkillRequest {
    let mut meta = HashMap::new();
    meta.insert("reply_to".to_string(), "gateway-replies-xyz".to_string());
    meta.insert("request_id".to_string(), "req-001".to_string());

    SkillRequest {
        skill: "code-complexity".to_string(),
        data: serde_json::json!({
            "code": "def foo(x):\n    for i in range(x):\n        if i % 2 == 0:\n            print(i)\n",
            "filename": "example.py"
        }),
        context: SkillContext {
            session_id: "session-abc123".to_string(),
            protocol: "a2a".to_string(),
        },
        metadata: meta,
    }
}

/// Build a realistic `SendTaskParams` fixture for serialisation benchmarks.
pub fn make_send_task_params() -> SendTaskParams {
    let mut meta = HashMap::new();
    meta.insert("skill".to_string(), "code-complexity".to_string());
    meta.insert("reply_to".to_string(), "gateway-replies-xyz".to_string());
    meta.insert("request_id".to_string(), "req-001".to_string());

    SendTaskParams {
        id: "task-001".to_string(),
        session_id: Some("session-001".to_string()),
        message: Message {
            role: "user".to_string(),
            parts: vec![Part::Text {
                text: "Analyse the complexity of this Python function: \
                       def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        \
                       for j in range(n-i-1):\n            if arr[j] > arr[j+1]:\n                \
                       arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr"
                    .to_string(),
            }],
        },
        metadata: Some(meta),
    }
}

/// Generate synthetic AGENTS.md content with `n` skill entries.
pub fn make_agents_md(n_skills: usize) -> String {
    let mut s = String::from(
        "# Test Agent\n\n\
         Handles test tasks for benchmarking.\n\n\
         <available_skills>\n\n",
    );
    for i in 0..n_skills {
        s.push_str(&format!(
            "<skill>\n  \
               <name>skill-{i}</name>\n  \
               <description>Performs analysis task {i} with AST metrics and LLM-powered review.</description>\n  \
               <location>.claude/skills/skill-{i}/</location>\n\
             </skill>\n\n"
        ));
    }
    s.push_str("</available_skills>\n");
    s
}

/// Map a category name to a Kafka topic name (mirrors gateway logic).
#[inline]
pub fn category_to_topic(category: &str) -> String {
    format!("TOPIC_{}", category.replace('-', "_").to_uppercase())
}
