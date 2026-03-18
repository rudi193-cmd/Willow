import uuid

class ReviewNode:
    def __init__(self, node_id):
        self.node_id = node_id
        self.reviews = {}

class ReviewGraph:
    def __init__(self):
        self.nodes = {}

    def add_node(self, node_id):
        self.nodes[node_id] = ReviewNode(node_id)

    def request_review(self, node_id, action):
        """Request a lateral peer review from a node.

        Args:
            node_id (str): ID of the node requesting the review.
            action (str): Action being reviewed (e.g., 'proposal', 'transaction').

        Returns:
            str: Unique ID for the review.
        """
        review_id = str(uuid.uuid4())
        review_node = ReviewNode(None)
        review_node.action = action

        self.nodes[node_id].reviews[review_id] = review_node

        # Perform 1-of-1 quorum for review creation
        if len(self.nodes[node_id].reviews) == 1:
            self.nodes[node_id].action = action

        return review_id

    def answer_review(self, review_id, decision):
        """Answer a lateral peer review.

        Args:
            review_id (str): ID of the review being answered.
            decision (bool): Decision on the review (True = approve, False = reject).

        Returns:
            bool: Whether the decision was successful.
        """
        review_node = self.nodes.get(list(self.nodes.values())[0].node_id).reviews.get(review_id)
        if review_node:
            if self.is_review_quorated(review_id):
                self.propagate_review_decision(review_id, decision)
                return True
            else:
                return False
        return False

    def is_review_quorated(self, review_id):
        """Check if a review has reached the required quorum.

        Args:
            review_id (str): ID of the review to check.

        Returns:
            bool: Whether the review has reached the required quorum.
        """
        review_node = self.nodes.get(list(self.nodes.values())[0].node_id).reviews.get(review_id)
        if review_node:
            num_approvals = 0
            num_rejections = 0

            for node in self.nodes.values():
                if review_id in node.reviews:
                    review = node.reviews[review_id]
                    if review.action == review_node.action:
                        if review.decision:
                            num_approvals += 1
                        else:
                            num_rejections += 1

            if num_approvals == 1 and len(self.nodes) == 1:  # 1-of-1 quorum
                return True
            elif num_approvals == (len(self.nodes)/3)*2 and len(self.nodes) ==3:  # 2-of-3 quorum
                return True
            else:
                return False
        return False

    def propagate_review_decision(self, review_id, decision):
        """Propagate the decision of a review to its neighboring reviews.

        Args:
            review_id (str): ID of the review being answered.
            decision (bool): Decision on the review (True = approve, False = reject).
        """
        review_node = self.nodes.get(list(self.nodes.values())[0].node_id).reviews.get(review_id)
        if review_node:
            # Propagate review decision backward
            for node in self.nodes.values():
                for review in node.reviews.values():
                    if review.action == review_node.action and review_id != review.review_id:
                        review.decision = decision
                        self.propagate_review_decision(review.review_id, decision)

            # Propagate review decision forward (default deny)
            for review in self.nodes[list(self.nodes.values())[0].node_id].reviews.values():
                if review.action == review_node.action:
                    review.decision = not decision
