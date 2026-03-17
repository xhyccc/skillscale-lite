//! **skill_parsing** — benchmarks for AGENTS.md parsing (skill-discovery hot path).
//!
//! At startup the gateway and skill-server both scan every `AGENTS.md` file under
//! the `skills/` tree.  `parse_agents_md()` splits on `<skill>` tags and calls
//! `extract_tag()` for each field.  These benchmarks measure the cost of that
//! parsing at varying numbers of skill entries.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use perf_eval::{extract_tag, make_agents_md, parse_agents_md};

// ── parse_agents_md ───────────────────────────────────────────────────────────

/// Benchmark end-to-end AGENTS.md parsing at four catalogue sizes.
fn bench_parse_agents_md(c: &mut Criterion) {
    let mut group = c.benchmark_group("skill_parsing/parse_agents_md");

    for &n in &[2_usize, 10, 50, 100] {
        let content = make_agents_md(n);
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::new("skills", n), &content, |b, content| {
            b.iter(|| {
                let skills = parse_agents_md("test-category", content);
                std::hint::black_box(skills);
            });
        });
    }

    group.finish();
}

/// Benchmark parsing a realistic two-skill AGENTS.md (matches actual repo fixture).
fn bench_parse_real_agents_md(c: &mut Criterion) {
    let content = r#"# Code Analysis Skill Server

This skill server handles code analysis tasks including complexity metrics,
dead code detection, and Python static analysis.

## Available Skills

<available_skills>

<skill>
  <name>code-complexity</name>
  <description>
    Analyzes Python source code complexity using AST metrics and LLM-powered
    review. Computes cyclomatic complexity, nesting depth, and function length,
    then provides intelligent refactoring suggestions via LLM.
  </description>
  <location>.claude/skills/code-complexity/</location>
</skill>

<skill>
  <name>dead-code-detector</name>
  <description>
    Detects dead code in Python source using AST analysis and LLM-powered
    review. Finds unused imports, unused variables, unreachable code, and
    empty functions, then provides intelligent cleanup suggestions via LLM.
  </description>
  <location>.claude/skills/dead-code-detector/</location>
</skill>

</available_skills>
"#;

    c.bench_function("skill_parsing/real_agents_md", |b| {
        b.iter(|| {
            let skills = parse_agents_md("code-analysis", content);
            std::hint::black_box(skills);
        });
    });
}

// ── extract_tag ───────────────────────────────────────────────────────────────

/// Benchmark individual `extract_tag` calls — called twice per skill entry.
fn bench_extract_tag(c: &mut Criterion) {
    let block = r#"
  <name>code-complexity</name>
  <description>
    Analyzes Python source code complexity using AST metrics and LLM-powered
    review. Computes cyclomatic complexity, nesting depth, and function length,
    then provides intelligent refactoring suggestions via LLM.
  </description>
  <location>.claude/skills/code-complexity/</location>"#;

    let mut group = c.benchmark_group("skill_parsing/extract_tag");

    group.bench_function("name", |b| {
        b.iter(|| {
            let r = extract_tag(block, "name");
            std::hint::black_box(r);
        });
    });

    group.bench_function("description", |b| {
        b.iter(|| {
            let r = extract_tag(block, "description");
            std::hint::black_box(r);
        });
    });

    group.bench_function("location", |b| {
        b.iter(|| {
            let r = extract_tag(block, "location");
            std::hint::black_box(r);
        });
    });

    group.finish();
}

criterion_group!(
    benches,
    bench_parse_agents_md,
    bench_parse_real_agents_md,
    bench_extract_tag,
);
criterion_main!(benches);
