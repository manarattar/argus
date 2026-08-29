/**
 * Next.js CLI wrapper.
 *
 * Applies the filesystem compatibility shim (see `fs-compat.mjs`) before
 * handing control to Next's own CLI, so `dev`, `build` and `start` work on
 * volumes that misreport `readlink` on regular files.
 *
 * Usage: node scripts/next.mjs <next-command> [...args]
 */

import './fs-compat.mjs';

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('usage: node scripts/next.mjs <dev|build|start|lint> [...args]');
  process.exit(1);
}

// Next's CLI reads process.argv directly, so reshape it to look like a normal
// `next <command>` invocation before importing.
process.argv = [process.argv[0], 'next', ...args];

await import('next/dist/bin/next');
