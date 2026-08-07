import fs from 'node:fs';
import path from 'node:path';
import { readJson, writeJson } from './util.js';

// Port of lib/services/snapshot_manager.dart
export class SnapshotManager {
  static cachePath(config) {
    return path.join(config.basePath, 'snapshot_cache.json');
  }

  static loadCache(config) {
    const data = readJson(SnapshotManager.cachePath(config), null);
    if (data && data.playlists) return data;
    return { playlists: {}, version: '1.0' };
  }

  static saveCache(config, cache) {
    writeJson(SnapshotManager.cachePath(config), cache);
  }

  static detectRemovedSongs(config, playlistName, currentTracks) {
    const cache = SnapshotManager.loadCache(config);
    const playlists = cache.playlists || {};
    const old = playlists[playlistName];
    if (!old) return [];
    const oldTracks = old.tracks || [];
    const oldSet = new Set(oldTracks);
    const currentSet = new Set(currentTracks);
    return oldTracks.filter((t) => !currentSet.has(t));
  }

  static processPlaylist(config, playlistName, currentTracks) {
    const removed = SnapshotManager.detectRemovedSongs(config, playlistName, currentTracks);
    const cache = SnapshotManager.loadCache(config);
    cache.playlists[playlistName] = {
      tracks: currentTracks,
      last_updated: new Date().toISOString(),
    };
    SnapshotManager.saveCache(config, cache);
    return removed.length;
  }
}
