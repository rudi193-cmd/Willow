import enum

class WorkflowState(enum.Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"

class WorkflowDetector:
    """
    Detects the current state of a workflow based on conversation history.

    The detection logic focuses on the "shape" of interactions, aiming to distinguish
    between a user actively engaged in a multi-step process (workflow execution)
    and a user who is exploring, asking one-off questions, or has completed
    a workflow.
    """

    def __init__(self, auto_detect_enabled: bool = True):
        """
        Initializes the WorkflowDetector.

        Args:
            auto_detect_enabled: If True, the detector will automatically infer
                                 the workflow state. If False, the state must be
                                 manually set.
        """
        self._auto_detect_enabled = auto_detect_enabled
        self._current_state = WorkflowState.INACTIVE  # Default state

    @property
    def auto_detect_enabled(self) -> bool:
        """Returns whether auto-detection is currently enabled."""
        return self._auto_detect_enabled

    def set_auto_detect_enabled(self, enabled: bool):
        """
        Enables or disables automatic workflow state detection.

        Args:
            enabled: True to enable auto-detection, False to disable.
        """
        self._auto_detect_enabled = enabled

    def set_manual_state(self, state: WorkflowState):
        """
        Manually sets the workflow state, overriding auto-detection.

        Args:
            state: The desired WorkflowState (WorkflowState.ACTIVE or WorkflowState.INACTIVE).
        """
        if not isinstance(state, WorkflowState):
            raise TypeError("state must be a WorkflowState enum member.")
        self._current_state = state
        self._auto_detect_enabled = False  # Manual state overrides auto-detection

    def get_workflow_state(self, conversation_history: list[dict] | None = None) -> WorkflowState:
        """
        Determines the current workflow state.

        If auto-detection is enabled, it analyzes the conversation history.
        If auto-detection is disabled, it returns the manually set state.

        Args:
            conversation_history: A list of message dictionaries. Each dictionary
                                  should ideally have at least a 'role' key ('user'
                                  or 'assistant') and a 'content' key.

        Returns:
            The current WorkflowState (WorkflowState.ACTIVE or WorkflowState.INACTIVE).
        """
        if not self._auto_detect_enabled:
            return self._current_state

        if conversation_history is None or not conversation_history:
            return WorkflowState.INACTIVE  # No history, assume inactive

        # --- Workflow Detection Logic (based on interaction shape) ---
        # This is a simplified example. Real-world implementations might involve:
        # - Analyzing patterns of user questions (e.g., asking for clarification,
        #   providing parameters in sequence).
        # - Tracking the number of turns in a potential workflow sequence.
        # - Looking for specific keywords or intents that indicate workflow steps.
        # - Using NLP models to classify message types (e.g., query vs. command).

        # Heuristic: If the last few messages show a back-and-forth that seems
        # like a structured process rather than isolated queries, consider it active.
        # For example, user asks a question, assistant responds, user provides more info
        # or asks a follow-up question directly related to the previous turn.

        active_threshold = 3  # Number of consecutive user/assistant turns to consider active
        if len(conversation_history) < active_threshold:
            return WorkflowState.INACTIVE

        # Count consecutive "engaged" turns.
        # This is a very basic interpretation of "shape".
        # A more sophisticated approach would analyze the *content* and *intent*
        # of the messages to see if they form a coherent, multi-step process.
        consecutive_engaged_turns = 0
        for i in range(len(conversation_history) - 1, -1, -1):
            message = conversation_history[i]
            if message.get("role") == "user" or message.get("role") == "assistant":
                consecutive_engaged_turns += 1
            else:
                # If we encounter a message that's not user or assistant,
                # it breaks the potential workflow sequence for this heuristic.
                break

