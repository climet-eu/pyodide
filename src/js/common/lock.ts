/**
 * @returns A new asynchronous lock
 * @private
 */
export function createLock() {
  // This is a promise that is resolved when the lock is open, not resolved when lock is held.
  let _lock = Promise.resolve();
  let _isLocked = false;

  /**
   * Acquire the async lock
   * @returns A zero argument function that releases the lock.
   * @private
   */
  async function acquireLock() {
    const old_lock = _lock;
    let releaseLock: () => void;
    _lock = new Promise((resolve) => (releaseLock = () => { _isLocked = false; resolve(); }));
    await old_lock;
    if (_isLocked) {
      throw new Error("cannot asynchronously acquire the lock");
    }
    _isLocked = true;
    // @ts-ignore
    return releaseLock;
  }

  /**
   * Execute the synchronous inner callback while the lock is held
   * @param inner callback
   * @private
   */
  function withLockSync<A extends any[], T>(inner: (...args: A) => T, ...args: A): T {
    if (_isLocked) {
      throw new Error("cannot synchronously acquire the lock");
    }
    // the lock is not re-entrant
    _isLocked = true;

    let result: T;

    try {
      result = inner(...args);
    } finally {
      _isLocked = false;
    }

    return result;
  }
  acquireLock.withLockSync = withLockSync;

  return acquireLock;
}
