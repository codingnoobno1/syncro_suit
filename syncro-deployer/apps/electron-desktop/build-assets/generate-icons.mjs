#!/usr/bin/env node
/**
 * Generates crisp 512x512 PNG (build-assets/icon.png) and 256x256 PNG-in-ICO
 * (build-assets/icon.ico) using zero external dependencies so electron-builder
 * packages cleanly across Windows, Linux, and macOS CI runners.
 */
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function pngChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, 'ascii');
  const crcBuf = Buffer.alloc(4);
  crcBuf.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  return Buffer.concat([len, typeBuf, data, crcBuf]);
}

function renderIconPng(size) {
  const raw = Buffer.alloc(size * (size * 4 + 1));
  const cx = size / 2;
  const cy = size / 2;
  const rCorner = size * 0.19;

  for (let y = 0; y < size; y++) {
    const rowStart = y * (size * 4 + 1);
    raw[rowStart] = 0; // filter: None
    for (let x = 0; x < size; x++) {
      const px = rowStart + 1 + x * 4;
      // Rounded-square mask
      const dx = Math.max(0, Math.abs(x - cx) - (size / 2 - rCorner));
      const dy = Math.max(0, Math.abs(y - cy) - (size / 2 - rCorner));
      const distCorner = Math.hypot(dx, dy);
      if (distCorner > rCorner) {
        raw[px] = 0;
        raw[px + 1] = 0;
        raw[px + 2] = 0;
        raw[px + 3] = 0;
        continue;
      }

      // Base obsidian slate canvas
      let r = 15, g = 20, b = 26, a = 255;

      // Subtle inner hairline frame
      const edgeDist = Math.min(x, y, size - 1 - x, size - 1 - y);
      if (edgeDist >= size * 0.045 && edgeDist <= size * 0.06) {
        r = 35; g = 49; b = 64;
      }

      // Hexagonal Syncro precision emblem
      const nx = (x - cx) / (size * 0.24);
      const ny = (y - (cy - size * 0.04)) / (size * 0.24);
      const hexDist = Math.max(Math.abs(nx), Math.abs(nx) * 0.5 + Math.abs(ny) * 0.8660254);

      if (hexDist >= 0.78 && hexDist <= 1.0) {
        // Cerulean steel outer hexagon
        r = 34; g = 168; b = 189;
      } else if (hexDist >= 0.42 && hexDist < 0.78) {
        r = 22; g = 40; b = 52;
        if (hexDist >= 0.56 && hexDist <= 0.64) {
          r = 69; g = 200; b = 220;
        }
      } else if (Math.hypot(nx, ny) <= 0.22) {
        r = 34; g = 168; b = 189;
      }

      // Emerald bottom chevron accent bar
      const by = (y - (cy + size * 0.27)) / (size * 0.06);
      const bx = Math.abs((x - cx) / (size * 0.23));
      if (bx <= 1.0 && Math.abs(by - (1.0 - bx) * 0.7) <= 0.42) {
        r = 54; g = 179; b = 126;
      }

      raw[px] = r;
      raw[px + 1] = g;
      raw[px + 2] = b;
      raw[px + 3] = a;
    }
  }

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;

  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const idat = zlib.deflateSync(raw, { level: 9 });
  return Buffer.concat([
    signature,
    pngChunk('IHDR', ihdr),
    pngChunk('IDAT', idat),
    pngChunk('IEND', Buffer.alloc(0)),
  ]);
}

function wrapPngAsIco(pngBuf) {
  // Valid Vista+ PNG-encoded 256x256 ICO container
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // ICO type
  header.writeUInt16LE(1, 4); // 1 image

  const entry = Buffer.alloc(16);
  entry[0] = 0; // 256px width
  entry[1] = 0; // 256px height
  entry[2] = 0; // color palette
  entry[3] = 0; // reserved
  entry.writeUInt16LE(1, 4); // planes
  entry.writeUInt16LE(32, 6); // bpp
  entry.writeUInt32LE(pngBuf.length, 8); // bytes in resource
  entry.writeUInt32LE(22, 12); // offset (6 + 16)

  return Buffer.concat([header, entry, pngBuf]);
}

const png512 = renderIconPng(512);
const png256 = renderIconPng(256);
const ico256 = wrapPngAsIco(png256);

fs.writeFileSync(path.join(__dirname, 'icon.png'), png512);
fs.writeFileSync(path.join(__dirname, 'icon.ico'), ico256);
console.log(`Generated icon.png (${png512.length} B) and icon.ico (${ico256.length} B)`);
