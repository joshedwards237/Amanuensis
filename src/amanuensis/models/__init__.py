"""Value objects. They know what a thing *is*; they do not drive flow.

Nothing in this package imports a controller, an engine, or a UI toolkit. The
dependency runs one way, which is what lets a stored transcript be replayed
through a post-processing chain without a daemon (PRD §6.3).
"""
