"""Command-line interface for running evals."""
from pathlib import Path
from typing import Annotated, Optional

import typer

from sdk.datasets import load_dataset
from sdk.sinks import JsonFileSink, LangfuseSink, StdoutSink
from runner.engine import run_eval


def main(
    registry: Annotated[Path, typer.Option("--registry", "-r", help="Path to registry.yaml")],
    eval_id: Annotated[str, typer.Option("--eval", "-e", help="Eval ID to run")],
    dataset: Annotated[Path, typer.Option("--dataset", "-d", help="Path to dataset JSONL (with outputs)")],
    agent_name: Annotated[str, typer.Option("--agent-name", help="Name of the agent being evaluated")],
    agent_version: Annotated[str, typer.Option("--agent-version", help="Version/commit of the agent")],
    env: Annotated[str, typer.Option("--env", help="Environment (local, ci, prod)")] = "local",
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Output directory for JSON results")] = None,
    langfuse: Annotated[bool, typer.Option("--langfuse", help="Send scores to Langfuse")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Minimal output")] = False,
):
    """
    AI Evals CLI - Run evals on agent outputs.
    
    **Phase 1 Workflow:**
    1. Agent runs on dataset inputs and populates output field
    2. Dataset JSONL now has: {id, input, output, expected}
    3. Run evals: ai-evals -r registry.yaml -e eval_id -d dataset.jsonl --agent-name my-agent --agent-version v1.0
    
    **Examples:**
        # Local evaluation
        ai-evals -r registry.yaml -e groundedness.v1 -d dataset_with_outputs.jsonl \\
          --agent-name my-agent --agent-version abc123
        
        # CI evaluation with JSON export
        ai-evals -r registry.yaml -e contains_check.v1 -d dataset.jsonl \\
          --agent-name my-agent --agent-version $GIT_SHA --env ci -o results/
        
        # Production evaluation (dataset has no expected values)
        ai-evals -r registry.yaml -e groundedness.v1 -d prod_outputs.jsonl \\
          --agent-name my-agent --agent-version v2.1.0 --env prod --langfuse
    """
    # Load dataset
    try:
        typer.echo(f"Loading dataset from: {dataset}")
        dataset_items = load_dataset(dataset)
        typer.echo(f"Loaded {len(dataset_items)} dataset item(s)")
    except Exception as e:
        typer.echo(f"Error loading dataset: {e}", err=True)
        raise typer.Exit(1)

    # Build sinks
    sinks = []
    if not quiet:
        sinks.append(StdoutSink(pretty=True))

    if output:
        sinks.append(JsonFileSink(output))

    if langfuse:
        sinks.append(LangfuseSink())

    if not sinks:
        sinks.append(StdoutSink(pretty=False))

    # Run eval
    try:
        typer.echo(f"Running eval: {eval_id}")
        typer.echo(f"Agent: {agent_name} (version: {agent_version})")
        typer.echo(f"Environment: {env}")
        
        run_eval(
            registry_path=registry,
            eval_id=eval_id,
            dataset=dataset_items,
            agent_name=agent_name,
            agent_version=agent_version,
            env=env,
            sinks=sinks,
        )
    except Exception as e:
        typer.echo(f"Error running eval: {e}", err=True)
        raise typer.Exit(1)


app = typer.Typer()
app.command()(main)


if __name__ == "__main__":
    app()
