"""Base agent class for all specialized agents.

Defines the abstract base class that all incident analysis agents inherit from.
Agents analyze specific aspects of incidents (logs, metrics, events, etc.).
"""

# TODO: Import ABC, abstractmethod from abc
# TODO: Import typing components (Any, Dict, List, Optional)
# TODO: Import datetime
# TODO: Import AnalysisResult, SeverityLevel from models
# TODO: Import setup_logger


class BaseAgent:
    """Base class for incident analysis agents.
    
    All agents should inherit from this class and implement the analyze method.
    Provides common utilities for result creation and data processing.
    
    Attributes:
        name (str): Agent identifier/name
        description (str): Human-readable agent description
        logger: Configured logger instance
    """
    
    def __init__(self, name: str, description: str = ""):
        """Initialize the agent.
        
        Args:
            name (str): Agent name/identifier (e.g., 'log_analyzer')
            description (str): Human-readable description of agent purpose
        """
        # TODO: Store name and description
        # TODO: Setup logger with agent name
        pass
    
    async def analyze(self, data: dict):
        """Analyze incident data.
        
        Args:
            data (dict): Input data for analysis (logs, metrics, events, etc.)
            
        Returns:
            AnalysisResult: Analysis findings with severity and confidence
            
        Note:
            This is the main method that must be implemented by subclasses.
            Should perform domain-specific analysis on the input data.
        """
        # TODO: Implement in subclass
        pass
    
    async def preprocess(self, data: dict) -> dict:
        """Preprocess input data before analysis.
        
        Args:
            data (dict): Raw input data
            
        Returns:
            dict: Preprocessed data ready for analysis
        """
        # TODO: Implement preprocessing if needed (cleaning, normalization, etc.)
        pass
    
    async def postprocess(self, result):
        """Post-process analysis results.
        
        Args:
            result: Raw analysis result
            
        Returns:
            Analysis result with post-processing applied
        """
        # TODO: Implement post-processing if needed (filtering, aggregation, etc.)
        pass
    
    def _create_result(self, findings: list, severity=None, confidence: float = 0.5, data: dict = None):
        """Create a standardized analysis result.
        
        Args:
            findings (list): List of finding strings
            severity: Severity level from SeverityLevel enum
            confidence (float): Confidence score (0-1)
            data (dict): Additional analysis data/metadata
            
        Returns:
            AnalysisResult: Formatted analysis result
        """
        # TODO: Instantiate AnalysisResult with provided data
        # TODO: Set timestamp to current UTC time
        # TODO: Return formatted result
        pass
