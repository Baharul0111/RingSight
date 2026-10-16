// Set HEALTH_URL in Worker Settings → Variables. No access key is needed.
export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil((async () => {
      const response = await fetch(env.HEALTH_URL, {signal: AbortSignal.timeout(60000)});
      if (!response.ok) throw new Error(`RingSight health failed: HTTP ${response.status}`);
    })());
  }
};
