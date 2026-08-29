/**
 * Filesystem compatibility shim for volumes without symlink support.
 *
 * The problem
 * -----------
 * POSIX specifies that `readlink()` on a regular file fails with `EINVAL`, and
 * webpack relies on that: it probes every resolved path with `readlink` and
 * treats `EINVAL` as "this is an ordinary file, carry on".
 *
 * On Windows exFAT volumes, Node returns `EISDIR` instead. Webpack does not
 * recognise that as "not a symlink", so it propagates it and the build fails
 * with `EISDIR: illegal operation on a directory, readlink '<some source file>'`
 * for a file that is plainly not a directory.
 *
 * Reproduce it with:
 *   node -e "require('fs').readlinkSync('some-file-on-exfat')"   // EISDIR
 *   node -e "require('fs').readlinkSync('some-file-on-ntfs')"    // EINVAL
 *
 * The fix
 * -------
 * Translate that one error code back to the value the POSIX contract promises.
 * Nothing else is changed: real symlinks still resolve, genuine directory reads
 * still fail, and on any filesystem that already behaves correctly this shim
 * never fires.
 *
 * It is loaded only by the `dev`, `build` and `start` scripts in this package,
 * so it cannot affect anything at runtime in a deployed container (which runs on
 * a normal filesystem and never needs it).
 */

import fs from 'node:fs';

const AFFECTED = 'EISDIR';
const EXPECTED = 'EINVAL';

/** True when the error is exFAT reporting a plain file as a directory. */
function isSymlinkProbe(error) {
  return error && error.code === AFFECTED && error.syscall === 'readlink';
}

function translate(error) {
  error.code = EXPECTED;
  error.errno = -22;
  error.message = error.message.replace(AFFECTED, EXPECTED);
  return error;
}

const originalSync = fs.readlinkSync;
fs.readlinkSync = function patchedReadlinkSync(...args) {
  try {
    return originalSync.apply(this, args);
  } catch (error) {
    throw isSymlinkProbe(error) ? translate(error) : error;
  }
};

const originalAsync = fs.readlink;
fs.readlink = function patchedReadlink(...args) {
  const callback = args[args.length - 1];
  if (typeof callback !== 'function') {
    return originalAsync.apply(this, args);
  }
  args[args.length - 1] = (error, ...rest) => {
    callback(isSymlinkProbe(error) ? translate(error) : error, ...rest);
  };
  return originalAsync.apply(this, args);
};

const originalPromise = fs.promises.readlink;
fs.promises.readlink = async function patchedReadlinkPromise(...args) {
  try {
    return await originalPromise.apply(this, args);
  } catch (error) {
    throw isSymlinkProbe(error) ? translate(error) : error;
  }
};
