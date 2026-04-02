/**
 * CJS shim for until-async (ESM-only package).
 * until-async v3 is ESM-only but Jest runs in CommonJS mode.
 * This shim replicates the single exported function.
 */

async function until(callback) {
  try {
    return [null, await callback().catch((error) => { throw error; })];
  } catch (error) {
    return [error, null];
  }
}

module.exports = { until };
