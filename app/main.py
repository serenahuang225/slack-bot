"""Optional HTTP deployment: uvicorn app.main:api. Use one worker."""
from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler
from app.slack import build_app

api = FastAPI()
slack_app, daily = build_app()
handler = SlackRequestHandler(slack_app)


@api.get("/health")
def health():
    return {"status": "ok"}


@api.post("/slack/events")
async def events(request: Request):
    return await handler.handle(request)
