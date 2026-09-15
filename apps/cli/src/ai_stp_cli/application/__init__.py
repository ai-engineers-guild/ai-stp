"""In-process application services shared by expert commands and the task engine.

Click stays a parser. Handlers and the task engine call the same functions.
Nothing here reaches another command through a nested process.
"""
