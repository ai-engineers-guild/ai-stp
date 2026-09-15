"""In-process application services shared by expert commands and the task engine.

Click stays a parser. Handlers call these functions; a later task dispatcher
calls the same ones. Nothing here shells out to `ai-stp`.
"""
