//! **json_serialization** — benchmarks for JSON (de)serialization of core message types.
//!
//! Every request in SkillScale Lite passes through at least two serde_json calls:
//!   - `serde_json::to_string(&params)` in the gateway before Kafka produce
//!   - `serde_json::from_str::<Value>(payload)` in the reply consumer
//!
//! These benchmarks measure the cost of those operations so that performance
//! regressions in message types are caught early.

use criterion::{criterion_group, criterion_main, Criterion};
use perf_eval::{
    make_send_task_params, make_skill_request, SendTaskParams, SkillRequest,
};

// ── Serialization ─────────────────────────────────────────────────────────────

fn bench_serialize(c: &mut Criterion) {
    let req = make_skill_request();
    let params = make_send_task_params();

    let mut group = c.benchmark_group("json_serialization");

    group.bench_function("skill_request", |b| {
        b.iter(|| {
            let s = serde_json::to_string(&req).unwrap();
            std::hint::black_box(s);
        });
    });

    group.bench_function("send_task_params", |b| {
        b.iter(|| {
            let s = serde_json::to_string(&params).unwrap();
            std::hint::black_box(s);
        });
    });

    group.finish();
}

// ── Deserialization ───────────────────────────────────────────────────────────

fn bench_deserialize(c: &mut Criterion) {
    let req_json = serde_json::to_string(&make_skill_request()).unwrap();
    let params_json = serde_json::to_string(&make_send_task_params()).unwrap();

    let mut group = c.benchmark_group("json_deserialization");

    group.bench_function("skill_request", |b| {
        b.iter(|| {
            let r: SkillRequest = serde_json::from_str(&req_json).unwrap();
            std::hint::black_box(r);
        });
    });

    group.bench_function("send_task_params", |b| {
        b.iter(|| {
            let r: SendTaskParams = serde_json::from_str(&params_json).unwrap();
            std::hint::black_box(r);
        });
    });

    // The gateway's reply consumer parses to untyped `Value` first, then
    // navigates with `.get()` calls — benchmark that path too.
    group.bench_function("reply_payload_as_value", |b| {
        let reply = serde_json::json!({
            "result": "Analysis complete: 3 functions exceed complexity threshold.",
            "status": "ok",
            "metadata": {
                "request_id": "req-001",
                "reply_to": "gateway-replies-xyz"
            }
        })
        .to_string();
        b.iter(|| {
            let v: serde_json::Value = serde_json::from_str(&reply).unwrap();
            let req_id = v
                .get("metadata")
                .and_then(|m| m.get("request_id"))
                .and_then(|v| v.as_str())
                .unwrap_or("");
            std::hint::black_box(req_id);
        });
    });

    group.finish();
}

// ── Round-trip ────────────────────────────────────────────────────────────────

fn bench_roundtrip(c: &mut Criterion) {
    let req = make_skill_request();
    let params = make_send_task_params();

    let mut group = c.benchmark_group("json_roundtrip");

    group.bench_function("skill_request", |b| {
        b.iter(|| {
            let json = serde_json::to_string(&req).unwrap();
            let r: SkillRequest = serde_json::from_str(&json).unwrap();
            std::hint::black_box(r);
        });
    });

    group.bench_function("send_task_params", |b| {
        b.iter(|| {
            let json = serde_json::to_string(&params).unwrap();
            let r: SendTaskParams = serde_json::from_str(&json).unwrap();
            std::hint::black_box(r);
        });
    });

    group.finish();
}

criterion_group!(benches, bench_serialize, bench_deserialize, bench_roundtrip);
criterion_main!(benches);
