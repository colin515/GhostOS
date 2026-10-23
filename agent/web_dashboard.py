"""Authenticated LAN control plane. Never expose directly to the public internet."""
from __future__ import annotations
import asyncio
import ipaddress
import secrets
import socket
from urllib.parse import urlsplit
from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, ConfigDict, Field
from config import RESOURCE_DIR

class GoalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    goal: str = Field(min_length=1, max_length=16000)

class ApprovalRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    approved: bool


def allowed_peer(host):
    try:
        address = ipaddress.ip_address(host.split('%')[0])
        return address.is_loopback or address.is_private
    except ValueError:
        return False


def create_app(runtime):
    app = FastAPI(title='GhostOS Local Hub', docs_url=None, redoc_url=None, openapi_url=None)
    hostnames = ['localhost', '127.0.0.1', '[::1]', runtime.local_ip, socket.gethostname()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(set(hostnames)))

    def valid_token(value):
        return isinstance(value, str) and secrets.compare_digest(value, runtime.token)

    def valid_origin(origin, host):
        if not origin:
            return True  # CLI/native client; bearer authentication remains mandatory.
        return origin in (f'http://{host}', f'https://{host}')

    async def authenticate(request: Request, authorization: str | None):
        if not request.client or not allowed_peer(request.client.host):
            raise HTTPException(403, 'LAN clients only')
        if not valid_origin(request.headers.get('origin'), request.headers.get('host')):
            raise HTTPException(403, 'Cross-origin access refused')
        if not authorization or not authorization.startswith('Bearer ') or not valid_token(authorization[7:]):
            raise HTTPException(401, 'Pair using the token displayed in desktop settings')

    @app.get('/', response_class=HTMLResponse)
    async def index(request: Request):
        if not request.client or not allowed_peer(request.client.host):
            raise HTTPException(403, 'LAN only')
        return HTMLResponse((RESOURCE_DIR / 'ui' / 'dashboard.html').read_text(encoding='utf-8'),
                            headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                     'X-Content-Type-Options': 'nosniff',
                                     'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:; frame-ancestors 'none'"})

    @app.get('/api/state')
    async def state(request: Request, authorization: str | None = Header(default=None)):
        await authenticate(request, authorization)
        return {'running': runtime.running, 'tier': runtime.settings.tier,
                'pending': runtime.approvals.pending(), 'events': runtime.bus.after()[-80:]}

    @app.post('/api/goals', status_code=202)
    async def goal(payload: GoalRequest, request: Request, authorization: str | None = Header(default=None)):
        await authenticate(request, authorization)
        try:
            run_id = await run_in_threadpool(runtime.start, payload.goal)
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc
        return {'run': run_id}

    @app.post('/api/stop')
    async def stop(request: Request, authorization: str | None = Header(default=None)):
        await authenticate(request, authorization)
        await run_in_threadpool(runtime.stop)
        return {'stopped': True}

    @app.post('/api/approvals/{request_id}')
    async def approve(request_id: str, payload: ApprovalRequest, request: Request,
                      authorization: str | None = Header(default=None)):
        await authenticate(request, authorization)
        if not runtime.approve(request_id, payload.approved):
            raise HTTPException(409, 'Approval no longer pending')
        return {'resolved': True}

    @app.websocket('/ws')
    async def websocket(ws: WebSocket):
        if not ws.client or not allowed_peer(ws.client.host) or not valid_origin(ws.headers.get('origin'), ws.headers.get('host')):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            auth = await asyncio.wait_for(ws.receive_json(), timeout=5)
            if not isinstance(auth, dict) or not valid_token(auth.get('token')):
                await ws.close(code=1008)
                return
            cursor, frame_id = 0, 0
            while True:
                events = runtime.bus.after(cursor)
                if events:
                    cursor = events[-1]['id']
                frame = runtime.bus.latest_frame()
                payload = {'events': events, 'running': runtime.running,
                           'pending': runtime.approvals.pending()}
                if frame and frame['id'] > frame_id:
                    payload['frame'] = frame
                    frame_id = frame['id']
                # Slow clients disconnect rather than causing an unbounded frame queue.
                await asyncio.wait_for(ws.send_json(payload), timeout=3)
                await asyncio.sleep(0.25)
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
            try:
                await ws.close(code=1008)
            except RuntimeError:
                pass

    return app
