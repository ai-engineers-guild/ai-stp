"""Everything that talks to the platform.

Nothing else in the CLI opens a socket. The boundary is here so the offline
contour stays offline by construction rather than by discipline.
"""
