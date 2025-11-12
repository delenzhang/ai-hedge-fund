"""
Agent prompt contexts module.

This module contains all AI prompt strings extracted from agent files,
organized by agent name for better maintainability.
"""

from .warren_buffett import get_prompt_messages as get_warren_buffett_prompt
from .peter_lynch import get_prompt_messages as get_peter_lynch_prompt
from .ben_graham import get_prompt_messages as get_ben_graham_prompt
from .michael_burry import get_prompt_messages as get_michael_burry_prompt
from .charlie_munger import get_prompt_messages as get_charlie_munger_prompt
from .cathie_wood import get_prompt_messages as get_cathie_wood_prompt
from .bill_ackman import get_prompt_messages as get_bill_ackman_prompt
from .phil_fisher import get_prompt_messages as get_phil_fisher_prompt
from .mohnish_pabrai import get_prompt_messages as get_mohnish_pabrai_prompt
from .rakesh_jhunjhunwala import get_prompt_messages as get_rakesh_jhunjhunwala_prompt
from .stanley_druckenmiller import get_prompt_messages as get_stanley_druckenmiller_prompt
from .aswath_damodaran import get_prompt_messages as get_aswath_damodaran_prompt
from .portfolio_manager import get_prompt_messages as get_portfolio_manager_prompt

__all__ = [
    "get_warren_buffett_prompt",
    "get_peter_lynch_prompt",
    "get_ben_graham_prompt",
    "get_michael_burry_prompt",
    "get_charlie_munger_prompt",
    "get_cathie_wood_prompt",
    "get_bill_ackman_prompt",
    "get_phil_fisher_prompt",
    "get_mohnish_pabrai_prompt",
    "get_rakesh_jhunjhunwala_prompt",
    "get_stanley_druckenmiller_prompt",
    "get_aswath_damodaran_prompt",
    "get_portfolio_manager_prompt",
]

