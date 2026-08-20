import json as json_lib
import webbrowser

import typer
from rich.console import Console
from rich.table import Table

from gfs.config import load_settings
from gfs.core.service import ForkSyncService

app = typer.Typer(help="GitHub Fork Sync - sync forks with upstream")
console = Console()


def _get_service(config_path: str | None = None) -> ForkSyncService:
    settings = load_settings(config_path)
    settings.require_token()
    return ForkSyncService(settings)


@app.command()
def list(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    config: str = typer.Option(None, "--config", help="Path to config.yaml"),
):
    """List all fork repos and their sync status."""
    try:
        svc = _get_service(config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    forks = svc.list_forks()
    svc.close()

    if json_output:
        typer.echo(
            json_lib.dumps([f.model_dump() for f in forks], indent=2)
        )
        return

    table = Table(title="Fork Repositories")
    table.add_column("Repo", style="cyan")
    table.add_column("Upstream", style="magenta")
    table.add_column("Default Branch")
    table.add_column("URL")

    for f in forks:
        table.add_row(
            f.full_name,
            f.parent_full_name,
            f.default_branch,
            f.html_url,
        )
    console.print(table)


@app.command()
def diff(
    repo: str = typer.Argument(..., help="owner/repo of the fork"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    config: str = typer.Option(None, "--config", help="Path to config.yaml"),
):
    """Show detailed diff for a specific fork."""
    try:
        svc = _get_service(config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    forks = svc.list_forks()
    target = next((f for f in forks if f.full_name == repo), None)
    if not target:
        console.print(f"[red]Error:[/red] fork '{repo}' not found")
        raise typer.Exit(1)

    result = svc.diff(target)
    svc.close()

    if json_output:
        typer.echo(json_lib.dumps(result.model_dump(), indent=2))
        return

    console.print(f"[bold]repo:[/bold] {result.repo.full_name} (default: {result.repo.default_branch})")
    console.print(f"[bold]upstream:[/bold] {result.repo.parent_full_name} (default: {result.repo.parent_default_branch})")
    console.print(
        f"[bold]status:[/bold] {result.status}  | behind: {result.behind_by}  | ahead: {result.ahead_by}\n"
    )

    console.print(f"[yellow]=== 落后的 {result.behind_by} 个 commit（sync 后会合并进来）===[/yellow]")
    if result.behind_commits:
        for i, c in enumerate(result.behind_commits, 1):
            console.print(f"{i}. [{c.sha[:7]}] {c.message}  ({c.date[:10]}, {c.author})")
    else:
        console.print("（无）")

    console.print(f"\n[green]=== 超前的 {result.ahead_by} 个 commit（fork 独有）===[/green]")
    if result.ahead_commits:
        for i, c in enumerate(result.ahead_commits, 1):
            console.print(f"{i}. [{c.sha[:7]}] {c.message}  ({c.date[:10]}, {c.author})")
    else:
        console.print("（无）")


@app.command()
def sync(
    repo: str = typer.Argument(..., help="owner/repo of the fork"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    config: str = typer.Option(None, "--config", help="Path to config.yaml"),
):
    """Sync a fork with its upstream."""
    try:
        svc = _get_service(config)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    forks = svc.list_forks()
    target = next((f for f in forks if f.full_name == repo), None)
    if not target:
        console.print(f"[red]Error:[/red] fork '{repo}' not found")
        raise typer.Exit(1)

    d = svc.diff(target)
    if d.behind_by == 0:
        console.print(f"[yellow]{repo} is already up to date (behind_by=0)[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]repo:[/bold] {d.repo.full_name}")
    console.print(f"[bold]upstream:[/bold] {d.repo.parent_full_name}")
    console.print(f"status: {d.status}  | behind: {d.behind_by}  | ahead: {d.ahead_by}\n")
    console.print(f"[yellow]落后的 {d.behind_by} 个 commit：[/yellow]")
    for i, c in enumerate(d.behind_commits, 1):
        console.print(f"  {i}. [{c.sha[:7]}] {c.message}  ({c.date[:10]}, {c.author})")

    if not yes:
        confirm = typer.confirm("\n确认同步？", default=False)
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            raise typer.Exit(0)

    result = svc.sync(target)
    svc.close()

    if result.success:
        console.print(f"[green]OK {repo} synced successfully[/green]")
        console.print(f"  {result.message}")
    else:
        console.print(f"[red]FAIL {repo} sync failed (HTTP {result.error_code})[/red]")
        console.print(f"  {result.message}")
        raise typer.Exit(1)


@app.command()
def web(
    port: int = typer.Option(None, "--port", help="Port (default from config)"),
    config: str = typer.Option(None, "--config", help="Path to config.yaml"),
):
    """Start web interface."""
    settings = load_settings(config)

    port = port or settings.web_port
    url = f"http://127.0.0.1:{port}"
    if settings.github_token:
        console.print(f"[green]Starting web server at {url}[/green] (token loaded from env)")
    else:
        console.print(f"[green]Starting web server at {url}[/green] (no token, login page will be shown)")
    webbrowser.open(url)

    import uvicorn
    from gfs.web.app import create_app

    web_app = create_app(settings)
    uvicorn.run(web_app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    app()
