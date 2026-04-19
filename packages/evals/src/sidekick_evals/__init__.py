"""Sidekick evaluation suite."""
from .case_loader import TestCase, load_cases, load_cases_by_category
from .judge import judge_one
from .personas import PERSONAS, Persona, get_persona
from .rubric import RubricScore, aggregate, score
from .runner import run_evaluation
from .safety import SafetyReport, audit_response
from .simulator import SimulationResult, SimTurn, simulate_one

__all__ = [
    "TestCase",
    "load_cases",
    "load_cases_by_category",
    "judge_one",
    "RubricScore",
    "aggregate",
    "score",
    "run_evaluation",
    "Persona",
    "PERSONAS",
    "get_persona",
    "SimTurn",
    "SimulationResult",
    "simulate_one",
    "SafetyReport",
    "audit_response",
]
