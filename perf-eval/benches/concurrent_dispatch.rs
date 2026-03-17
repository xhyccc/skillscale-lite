//! **concurrent_dispatch** — benchmarks for the gateway's request-dispatch pattern.
//!
//! The SkillScale gateway keeps a `Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>>`
//! called `pending_requests`.  For every incoming HTTP request it:
//!   1. Generates a UUID request_id
//!   2. Creates a `tokio::sync::oneshot` channel
//!   3. Inserts the sender into the map under the request_id
//!   4. Produces a Kafka message (not benchmarked here — requires a broker)
//!   5. Awaits the receiver (unblocked by the background reply consumer)
//!
//! These benchmarks isolate and stress-test steps 1-3 and 5 at various
//! concurrency levels using a simulated in-process "responder" task.

use criterion::{criterion_group, criterion_main, BenchmarkId, Criterion, Throughput};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use tokio::sync::oneshot;
use uuid::Uuid;

// ── Runtime helper ────────────────────────────────────────────────────────────

fn build_runtime() -> tokio::runtime::Runtime {
    tokio::runtime::Builder::new_multi_thread()
        .worker_threads(4)
        .enable_all()
        .build()
        .expect("Failed to build Tokio runtime")
}

// ── Type alias ────────────────────────────────────────────────────────────────

type PendingMap = Arc<Mutex<HashMap<String, oneshot::Sender<Value>>>>;

// ── Benchmark helpers ─────────────────────────────────────────────────────────

/// Simulate one full request-response cycle:
///   - insert a oneshot sender into the shared map
///   - spawn an async "responder" task that immediately resolves it
///   - await the receiver
async fn single_dispatch_cycle(pending: PendingMap) {
    let request_id = Uuid::new_v4().to_string();
    let (tx, rx) = oneshot::channel::<Value>();

    {
        let mut map = pending.lock().unwrap();
        map.insert(request_id.clone(), tx);
    }

    // Simulate the reply consumer resolving the request
    let pending_resp = pending.clone();
    let req_id_resp = request_id.clone();
    tokio::spawn(async move {
        let tx = {
            let mut map = pending_resp.lock().unwrap();
            map.remove(&req_id_resp)
        };
        if let Some(tx) = tx {
            let _ = tx.send(serde_json::json!({"result": "ok", "request_id": req_id_resp}));
        }
    });

    let _ = rx.await;
}

// ── Benchmarks ────────────────────────────────────────────────────────────────

/// Benchmark: N *concurrent* request-response cycles sharing one pending map.
///
/// All N requester tasks are spawned at once; a corresponding set of N
/// responder tasks resolve them.  Measures end-to-end throughput as N scales.
fn bench_concurrent_dispatch(c: &mut Criterion) {
    let rt = build_runtime();

    let mut group = c.benchmark_group("concurrent_dispatch");

    for &n in &[1_usize, 10, 50, 100, 500] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::new("tasks", n), &n, |b, &n| {
            b.iter(|| {
                rt.block_on(async {
                    let pending: PendingMap = Arc::new(Mutex::new(HashMap::new()));
                    let mut handles = Vec::with_capacity(n);
                    for _ in 0..n {
                        let p = pending.clone();
                        handles.push(tokio::spawn(single_dispatch_cycle(p)));
                    }
                    for h in handles {
                        let _ = h.await;
                    }
                });
            });
        });
    }

    group.finish();
}

/// Benchmark: sequential insert → resolve → remove operations on the pending map.
///
/// Isolates the raw HashMap + Mutex overhead without async scheduler noise.
fn bench_pending_map_ops(c: &mut Criterion) {
    let mut group = c.benchmark_group("pending_map_ops");

    for &n in &[10_usize, 100, 1000] {
        group.throughput(Throughput::Elements(n as u64));
        group.bench_with_input(BenchmarkId::new("entries", n), &n, |b, &n| {
            b.iter(|| {
                let pending: PendingMap = Arc::new(Mutex::new(HashMap::new()));

                // Phase 1: insert all senders
                let mut ids = Vec::with_capacity(n);
                let mut receivers = Vec::with_capacity(n);
                for _ in 0..n {
                    let id = Uuid::new_v4().to_string();
                    let (tx, rx) = oneshot::channel::<Value>();
                    ids.push(id.clone());
                    receivers.push(rx);
                    pending.lock().unwrap().insert(id, tx);
                }

                // Phase 2: remove all senders and fire them (simulated reply consumer)
                for id in &ids {
                    if let Some(tx) = pending.lock().unwrap().remove(id) {
                        let _ = tx.send(serde_json::json!({"result": "ok"}));
                    }
                }

                std::hint::black_box(receivers);
            });
        });
    }

    group.finish();
}

/// Benchmark: Kafka topic name generation from a category string.
///
/// This is a hot path in the gateway: every A2A request calls
/// `format!("TOPIC_{}", category.replace('-', "_").to_uppercase())`.
fn bench_topic_name_generation(c: &mut Criterion) {
    let categories = [
        "code-analysis",
        "data-processing",
        "text-processing",
        "image-analysis",
        "sentiment-analysis",
    ];

    c.bench_function("topic_name_from_category", |b| {
        let mut i = 0usize;
        b.iter(|| {
            let cat = categories[i % categories.len()];
            let topic = perf_eval::category_to_topic(cat);
            i += 1;
            std::hint::black_box(topic);
        });
    });
}

/// Benchmark: UUID v4 generation — used for every request_id and reply_topic.
fn bench_uuid_generation(c: &mut Criterion) {
    c.bench_function("uuid_v4_generation", |b| {
        b.iter(|| {
            let id = Uuid::new_v4().to_string();
            std::hint::black_box(id);
        });
    });
}

criterion_group!(
    benches,
    bench_concurrent_dispatch,
    bench_pending_map_ops,
    bench_topic_name_generation,
    bench_uuid_generation,
);
criterion_main!(benches);
