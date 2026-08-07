# -*- coding: utf-8 -*-
"""Brain 3: Performance Analysis Engine (Microservice Client) - Normalized v3.0.0
Note: Original brain3_ai_engine.py already handles Brain 3 registration.
This file provides a secondary entry point for the performance microservice.
Does NOT register Brain 3 to avoid duplicate registration.
"""
import os, sys
from typing import List, Dict
try:
    from . import BaseBrain, BrainResult, BrainIssue
except ImportError:
    try:
        from brains import BaseBrain, BrainResult, BrainIssue
    except ImportError:
        BaseBrain = object
        BrainResult = None
        BrainIssue = None

class Brain3PerformanceHelper:
    """Performance analysis helper - used by Brain3 AI engine for perf-specific scans."""
    name = "brain3_perf_helper"
    description = "Performance analysis helper (no separate registration)"
    
    @staticmethod
    def analyze_performance(project_path: str, config: dict) -> Dict:
        """Analyze performance issues - can be called by Brain3 main engine."""
        from core.brain_client import call_brain_service
        result = call_brain_service("3", 8613, project_path, config, {".py", ".js", ".ts"}, {"__pycache__", ".git"})
        return result
