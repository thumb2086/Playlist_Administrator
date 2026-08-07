import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import { stemOf } from './util.js';

// Port of _cleanupMp3 from lib/cli_main.dart
export async function cleanupMp3(libPath) {
  const m4aDir = path.join(libPath, 'm4a');
  const mp3Dir = path.join(libPath, 'mp3');
  if (!fs.existsSync(m4aDir) || !fs.existsSync(mp3Dir)) {
    console.log('錯誤：找不到 mp3 或 m4a 目錄');
    return;
  }

  const m4aStems = new Set();
  for (const f of fs.readdirSync(m4aDir)) {
    if (f.toLowerCase().endsWith('.m4a')) {
      m4aStems.add(stemOf(f).toLowerCase());
    }
  }
  console.log(`M4A 檔案數: ${m4aStems.size}`);

  const orphans = [];
  for (const f of fs.readdirSync(mp3Dir)) {
    if (f.toLowerCase().endsWith('.mp3')) {
      const stem = stemOf(f).toLowerCase();
      if (!m4aStems.has(stem)) {
        orphans.push(path.join(mp3Dir, f));
      }
    }
  }

  if (orphans.length === 0) {
    console.log('✅ 沒有發現孤兒 MP3');
    return;
  }

  console.log(`\n⚠️  找到 ${orphans.length} 個 metadata 更名版的孤兒 MP3：\n`);
  let totalSize = 0;
  for (const f of orphans) {
    const stat = fs.statSync(f);
    totalSize += stat.size;
    console.log(`  ${path.basename(f)}  (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
  }
  console.log(`\n  總計: ${(totalSize / 1024 / 1024).toFixed(1)} MB\n`);

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await new Promise((resolve) => rl.question('是否刪除？(y/N): ', resolve));
  rl.close();
  const input = (answer || '').trim().toLowerCase();
  if (input === 'y') {
    let deleted = 0;
    for (const f of orphans) {
      fs.unlinkSync(f);
      deleted++;
    }
    console.log(`✅ 已刪除 ${deleted} 個檔案`);
  } else {
    console.log('跳過刪除');
  }
}