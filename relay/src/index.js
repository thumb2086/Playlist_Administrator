import { DurableObject } from "cloudflare:workers";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/jam") {
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("Jam Relay", { status: 426 });
      }
      const id = env.JAM_ROOMS.idFromName("jam-relay");
      return env.JAM_ROOMS.get(id).fetch(request);
    }
    if (url.pathname === "/health") return new Response("ok");
    return new Response("Jam Relay v1");
  },
};

export class JamRoom extends DurableObject {
  constructor(state, env) {
    super(state, env);
    this.clients = new Map();
    this.roomCode = "";
    this.rs = this._empty();
  }

  _empty() {
    return {
      code: "", members: [], queue: [], current: null,
      playing: false, time: 0, ts: 0, chat: [],
      skipVotes: 0, skipNeeded: 1,
    };
  }

  async fetch(request) {
    const pair = new WebSocketPair();
    this.ctx.acceptWebSocket(pair[1]);
    return new Response(null, { status: 101, webSocket: pair[0] });
  }

  async webSocketMessage(ws, raw) {
    let msg;
    try { msg = JSON.parse(raw); } catch { return; }

    if (msg.type === "create") {
      const code = this._genCode();
      this.roomCode = code;
      const mid = this._genId();
      this.clients.set(ws, { id: mid, name: msg.name || "我", isHost: true });
      this.rs.code = code;
      this.rs.members = [{ id: mid, name: msg.name || "我", isHost: true }];
      ws.send(JSON.stringify({ type: "welcome", yourId: mid, state: { ...this.rs } }));
      return;
    }

    if (msg.type === "join") {
      if ((msg.code || "").toUpperCase().trim() !== this.roomCode) {
        ws.send(JSON.stringify({ type: "error", message: "房間代碼錯誤" }));
        return;
      }
      if (this.clients.size >= 30) {
        ws.send(JSON.stringify({ type: "error", message: "房間已滿" }));
        return;
      }
      const mid = this._genId();
      const m = { id: mid, name: msg.name || "你", isHost: false };
      this.clients.set(ws, { id: mid, name: m.name, isHost: false });
      this.rs.members.push(m);
      ws.send(JSON.stringify({ type: "welcome", yourId: mid, state: { ...this.rs } }));
      this._broadcast({ type: "member_joined", member: m }, ws);
      this._bcast({ type: "skip_count", count: this.rs.skipVotes, needed: this.rs.skipNeeded });
      return;
    }

    const info = this.clients.get(ws);
    if (!info) return;

    if (info.isHost) {
      if (msg.type === "progress") { this.rs.time = msg.pos || 0; this.rs.ts = msg.ts || Date.now(); this.rs.playing = true; }
      if (msg.type === "play") { this.rs.playing = true; this.rs.ts = Date.now(); }
      if (msg.type === "pause") { this.rs.playing = false; this.rs.ts = Date.now(); }
      if (msg.type === "seek") { this.rs.time = msg.pos || 0; this.rs.ts = Date.now(); }
      if (msg.type === "track_change") { this.rs.current = msg.current; this.rs.playing = msg.playing ?? true; this.rs.time = msg.pos || 0; this.rs.ts = msg.ts || Date.now(); }
      if (msg.type === "queue_update") { this.rs.queue = msg.queue || []; }
      if (msg.type === "skip_count") { this.rs.skipVotes = msg.count || 0; this.rs.skipNeeded = msg.needed || 1; }
    }

    const fwd = { ...msg, senderId: info.id };
    this._broadcast(fwd);
  }

  async webSocketClose(ws) { await this._remove(ws); }
  async webSocketError(ws) { await this._remove(ws); }

  async _remove(ws) {
    const info = this.clients.get(ws);
    if (!info) return;
    this.clients.delete(ws);
    this.rs.members = this.rs.members.filter((m) => m.id !== info.id);
    if (info.isHost && this.rs.members.length > 0) {
      this.rs.members[0].isHost = true;
    }
    if (this.rs.members.length === 0) {
      this.rs = this._empty();
      this.roomCode = "";
      return;
    }
    this._bcast({ type: "member_left", memberId: info.id });
    this._bcast({ type: "skip_count", count: this.rs.skipVotes, needed: Math.max(1, Math.ceil(this.rs.members.length / 2)) });
  }

  _broadcast(msg, exclude) {
    const data = JSON.stringify(msg);
    for (const [ws] of this.clients) {
      if (ws !== exclude) try { ws.send(data); } catch {}
    }
  }

  _bcast(msg) { this._broadcast(msg); }

  _genCode() {
    const c = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
    let r = "";
    for (let i = 0; i < 6; i++) r += c[Math.floor(Math.random() * c.length)];
    return r;
  }

  _genId() {
    return Math.random().toString(36).slice(2, 10);
  }
}
