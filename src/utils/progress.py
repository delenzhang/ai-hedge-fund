from datetime import datetime, timezone
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.style import Style
from rich.text import Text
from typing import Dict, Optional, Callable, List

console = Console()

# Import analyst config for display names
# Use lazy import to avoid circular dependencies
_ANALYST_CONFIG = None

def _get_analyst_config():
    """Lazy load ANALYST_CONFIG to avoid import issues."""
    global _ANALYST_CONFIG
    if _ANALYST_CONFIG is None:
        try:
            from src.utils.analysts import ANALYST_CONFIG
            _ANALYST_CONFIG = ANALYST_CONFIG
            # Verify it's not empty
            if not _ANALYST_CONFIG:
                import sys
                print("WARNING: ANALYST_CONFIG is empty after import", file=sys.stderr)
        except (ImportError, AttributeError) as e:
            # Fallback if import fails
            import sys
            print(f"WARNING: Failed to import ANALYST_CONFIG: {e}", file=sys.stderr)
            _ANALYST_CONFIG = {}
    return _ANALYST_CONFIG


class AgentProgress:
    """Manages progress tracking for multiple agents."""

    def __init__(self):
        self.agent_status: Dict[str, Dict[str, str]] = {}
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live = Live(self.table, console=console, refresh_per_second=4)
        self.started = False
        self.update_handlers: List[Callable[[str, Optional[str], str], None]] = []

    def register_handler(self, handler: Callable[[str, Optional[str], str], None]):
        """Register a handler to be called when agent status updates."""
        self.update_handlers.append(handler)
        return handler  # Return handler to support use as decorator

    def unregister_handler(self, handler: Callable[[str, Optional[str], str], None]):
        """Unregister a previously registered handler."""
        if handler in self.update_handlers:
            self.update_handlers.remove(handler)

    def start(self):
        """Start the progress display."""
        if not self.started:
            self.live.start()
            self.started = True

    def stop(self):
        """Stop the progress display."""
        if self.started:
            self.live.stop()
            self.started = False

    def update_status(self, agent_name: str, ticker: Optional[str] = None, status: str = "", analysis: Optional[str] = None):
        """Update the status of an agent."""
        if agent_name not in self.agent_status:
            self.agent_status[agent_name] = {"status": "", "ticker": None}

        if ticker:
            self.agent_status[agent_name]["ticker"] = ticker
        if status:
            self.agent_status[agent_name]["status"] = status
        if analysis:
            self.agent_status[agent_name]["analysis"] = analysis
        
        # Set the timestamp as UTC datetime
        timestamp = datetime.now(timezone.utc).isoformat()
        self.agent_status[agent_name]["timestamp"] = timestamp

        # Notify all registered handlers
        for handler in self.update_handlers:
            handler(agent_name, ticker, status, analysis, timestamp)

        self._refresh_display()

    def get_all_status(self):
        """Get the current status of all agents as a dictionary."""
        return {agent_name: {"ticker": info["ticker"], "status": info["status"], "display_name": self._get_display_name(agent_name)} for agent_name, info in self.agent_status.items()}

    def _get_display_name(self, agent_name: str) -> str:
        """Convert agent_name to a display-friendly format with Chinese/English."""
        # Handle portfolio_manager or portfolio_management_agent
        if "portfolio_manager" in agent_name or "portfolio_management" in agent_name:
            return "投资组合经理 / Portfolio Manager"
        
        # Handle risk_management_agent
        if "risk_management" in agent_name:
            return "风险管理 / Risk Management"
        
        # Get ANALYST_CONFIG (lazy loaded)
        ANALYST_CONFIG = _get_analyst_config()
        
        # If ANALYST_CONFIG is empty (import failed), fallback early
        if not ANALYST_CONFIG:
            base_key = agent_name.replace("_agent", "").replace("_analyst", "")
            # Debug output (temporary)
            import sys
            print(f"DEBUG: ANALYST_CONFIG is empty, agent_name={agent_name}, base_key={base_key}", file=sys.stderr)
            return base_key.replace("_", " ").title()
        
        # Try exact match first (agent_name might already be a key)
        if agent_name in ANALYST_CONFIG:
            return ANALYST_CONFIG[agent_name]["display_name"]
        
        # Try matching by removing _agent suffix (most common case)
        if agent_name.endswith("_agent"):
            base_key = agent_name[:-6]  # Remove "_agent" suffix
            if base_key in ANALYST_CONFIG:
                return ANALYST_CONFIG[base_key]["display_name"]
            # Debug output (temporary)
            import sys
            print(f"DEBUG: No match for agent_name={agent_name}, base_key={base_key}, available_keys={list(ANALYST_CONFIG.keys())[:5]}", file=sys.stderr)
        
        # Try matching by removing _analyst suffix
        if agent_name.endswith("_analyst"):
            base_key = agent_name[:-8]  # Remove "_analyst" suffix
            if base_key in ANALYST_CONFIG:
                return ANALYST_CONFIG[base_key]["display_name"]
        
        # Try matching by checking if agent_name ends with any key + "_agent"
        for key in ANALYST_CONFIG.keys():
            if agent_name == f"{key}_agent":
                return ANALYST_CONFIG[key]["display_name"]
            if agent_name.endswith(f"_{key}_agent"):
                return ANALYST_CONFIG[key]["display_name"]
        
        # Try matching with _analyst keys (e.g., technical_analyst_agent -> technical_analyst)
        for key in ANALYST_CONFIG.keys():
            if key.endswith("_analyst"):
                # Match patterns like: technical_analyst_agent, fundamentals_analyst_agent
                if agent_name == f"{key}_agent":
                    return ANALYST_CONFIG[key]["display_name"]
                # Also try without _analyst suffix: technical_agent -> technical_analyst
                base_without_analyst = key.replace("_analyst", "")
                if agent_name == f"{base_without_analyst}_agent":
                    return ANALYST_CONFIG[key]["display_name"]
        
        # Try matching news_sentiment (special case: news_sentiment_agent -> news_sentiment_analyst)
        if agent_name == "news_sentiment_agent" and "news_sentiment_analyst" in ANALYST_CONFIG:
            return ANALYST_CONFIG["news_sentiment_analyst"]["display_name"]
        
        # Fallback: try removing _agent and _analyst suffixes and match
        base_key = agent_name.replace("_agent", "").replace("_analyst", "")
        if base_key in ANALYST_CONFIG:
            return ANALYST_CONFIG[base_key]["display_name"]
        
        # Final fallback to original format if not found
        return base_key.replace("_", " ").title()

    def _refresh_display(self):
        """Refresh the progress display."""
        self.table.columns.clear()
        self.table.add_column(width=100)

        # Sort agents with Risk Management and Portfolio Management at the bottom
        def sort_key(item):
            agent_name = item[0]
            if "risk_management" in agent_name:
                return (2, agent_name)
            elif "portfolio_management" in agent_name:
                return (3, agent_name)
            else:
                return (1, agent_name)

        for agent_name, info in sorted(self.agent_status.items(), key=sort_key):
            status = info["status"]
            ticker = info["ticker"]
            # Create the status text with appropriate styling
            if status.lower() == "done":
                style = Style(color="green", bold=True)
                symbol = "✓"
            elif status.lower() == "error":
                style = Style(color="red", bold=True)
                symbol = "✗"
            else:
                style = Style(color="yellow")
                symbol = "⋯"

            agent_display = self._get_display_name(agent_name)
            status_text = Text()
            status_text.append(f"{symbol} ", style=style)
            status_text.append(f"{agent_display:<45}", style=Style(bold=True))

            if ticker:
                status_text.append(f"[{ticker}] ", style=Style(color="cyan"))
            status_text.append(status, style=style)

            self.table.add_row(status_text)


# Create a global instance
progress = AgentProgress()
