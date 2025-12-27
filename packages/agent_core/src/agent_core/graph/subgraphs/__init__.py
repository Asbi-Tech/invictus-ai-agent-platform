"""Multi-agent subgraphs for the Copilot system."""

from agent_core.graph.subgraphs.intent_analyzer import create_intent_analyzer_subgraph
from agent_core.graph.subgraphs.ask_handler import create_ask_handler_subgraph
from agent_core.graph.subgraphs.clarification import create_clarification_subgraph
from agent_core.graph.subgraphs.planning import create_planning_subgraph
from agent_core.graph.subgraphs.confirmation import create_confirmation_subgraph
from agent_core.graph.subgraphs.data_retrieval import create_data_retrieval_subgraph
from agent_core.graph.subgraphs.synthesis import create_synthesis_subgraph
from agent_core.graph.subgraphs.template_manager import create_template_manager_subgraph
from agent_core.graph.subgraphs.section_writer import create_section_writer_subgraph
from agent_core.graph.subgraphs.review import create_review_subgraph
from agent_core.graph.subgraphs.source_mapper import create_source_mapper_subgraph

__all__ = [
    "create_intent_analyzer_subgraph",
    "create_ask_handler_subgraph",
    "create_clarification_subgraph",
    "create_planning_subgraph",
    "create_confirmation_subgraph",
    "create_data_retrieval_subgraph",
    "create_synthesis_subgraph",
    "create_template_manager_subgraph",
    "create_section_writer_subgraph",
    "create_review_subgraph",
    "create_source_mapper_subgraph",
]
