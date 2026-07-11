"""
Eval Dataset
============
Seed dataset for the ARO quality gate: research questions with reference
key points a good answer must cover. Deliberately favors stable,
verifiable knowledge over fast-moving news so evaluations stay
meaningful over time.

Sync it to LangSmith with:  python -m evals.dataset
"""

import os

DATASET_NAME = os.getenv("ARO_EVAL_DATASET", "aro-research-quality")

EXAMPLES = [
    {
        "question": "What causes pulsar timing noise and how is it mitigated in pulsar timing arrays?",
        "key_points": [
            "intrinsic spin noise / rotational irregularities",
            "interstellar medium dispersion measure variations",
            "mitigation via multi-frequency observations and noise modeling",
        ],
    },
    {
        "question": "How does epoch folding improve the detection of periodic signals in radio astronomy?",
        "key_points": [
            "folding time series at a candidate period accumulates signal-to-noise",
            "chi-squared or H-test statistics evaluate folded profiles",
        ],
    },
    {
        "question": "What are the main approaches to detecting intrusions in IoT networks?",
        "key_points": [
            "signature-based vs anomaly-based detection",
            "flow-level and packet-level features",
            "machine learning classifiers (e.g. gradient boosting, neural networks)",
        ],
    },
    {
        "question": "What is a zero-trust architecture and what are its core principles?",
        "key_points": [
            "never trust, always verify",
            "least-privilege access",
            "continuous authentication / micro-segmentation",
        ],
    },
    {
        "question": "How do physics-informed neural networks differ from standard neural networks?",
        "key_points": [
            "physical laws (PDEs/ODEs) embedded in the loss function",
            "less training data needed; better extrapolation within physics constraints",
        ],
    },
    {
        "question": "What are the trade-offs between 4-bit quantization and full-precision inference for LLMs?",
        "key_points": [
            "large memory footprint reduction",
            "small accuracy degradation, task-dependent",
            "throughput/latency gains on constrained hardware",
        ],
    },
    {
        "question": "What is retrieval-augmented generation and why does it reduce hallucinations?",
        "key_points": [
            "retrieval of external documents grounds the generation",
            "citations become verifiable",
            "knowledge can be updated without retraining",
        ],
    },
    {
        "question": "How do vector databases perform approximate nearest neighbor search efficiently?",
        "key_points": [
            "HNSW graphs or IVF indexing",
            "trade recall for speed versus exact search",
        ],
    },
    {
        "question": "What are the primary failure modes of multi-agent LLM systems?",
        "key_points": [
            "error cascade / compounding hallucinations between agents",
            "coordination and termination failures",
            "cost/latency blowup from unbounded loops",
        ],
    },
    {
        "question": "Why is SHAP used for explaining gradient-boosted tree predictions?",
        "key_points": [
            "Shapley values give consistent, locally accurate feature attributions",
            "TreeSHAP computes them efficiently for tree ensembles",
        ],
    },
    {
        "question": "What is the difference between epistemic and aleatoric uncertainty in ML?",
        "key_points": [
            "epistemic: model/knowledge uncertainty, reducible with more data",
            "aleatoric: inherent data noise, irreducible",
        ],
    },
    {
        "question": "How does mTLS differ from regular TLS and when is it required?",
        "key_points": [
            "both client and server authenticate with certificates",
            "service-to-service auth in zero-trust / microservice environments",
        ],
    },
    {
        "question": "What are the benefits of LoRA fine-tuning over full fine-tuning?",
        "key_points": [
            "trains low-rank adapter matrices, freezing base weights",
            "orders of magnitude fewer trainable parameters and less VRAM",
            "adapters are swappable per task",
        ],
    },
    {
        "question": "How does an LSM tree optimize write-heavy database workloads?",
        "key_points": [
            "writes buffered in memory then flushed as sorted runs",
            "background compaction merges levels; reads may check multiple levels",
        ],
    },
    {
        "question": "What mechanisms does Kafka use to guarantee message durability?",
        "key_points": [
            "append-only replicated log with configurable acks",
            "in-sync replica set and leader election",
        ],
    },
]


def sync_to_langsmith() -> str:
    """Create (or update) the LangSmith dataset. Returns the dataset name."""
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        existing = {
            e.inputs.get("question")
            for e in client.list_examples(dataset_id=dataset.id)
        }
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="ARO research-quality gate: questions + reference key points.",
        )
        existing = set()

    new = [ex for ex in EXAMPLES if ex["question"] not in existing]
    if new:
        client.create_examples(
            inputs=[{"question": ex["question"]} for ex in new],
            outputs=[{"key_points": ex["key_points"]} for ex in new],
            dataset_id=dataset.id,
        )
    print(f"Dataset '{DATASET_NAME}': {len(EXAMPLES)} examples ({len(new)} added).")
    return DATASET_NAME


if __name__ == "__main__":
    sync_to_langsmith()
