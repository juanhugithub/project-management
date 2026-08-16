/**
 * 基于 URL hash 的轻量路由。
 * 路由不直接操作页面样式，入口文件在回调内决定激活标签和调用哪个页面加载函数。
 */

function normalizeRoute(route) {
  return String(route || "").replace(/^#?\/?/, "").replace(/\/$/, "");
}

export function createHashRouter({ defaultRoute = "dashboard" } = {}) {
  const routes = new Map();
  let started = false;

  function current() {
    return normalizeRoute(window.location.hash) || defaultRoute;
  }

  async function dispatch() {
    const route = current();
    const handler = routes.get(route) || routes.get(defaultRoute);
    if (handler) await handler(route);
    return route;
  }

  function navigate(route, { replace = false } = {}) {
    const target = normalizeRoute(route) || defaultRoute;
    const hash = `#/${target}`;
    if (replace) window.history.replaceState(null, "", hash);
    else if (window.location.hash !== hash) window.location.hash = hash;
    else dispatch();
  }

  function register(route, handler) {
    routes.set(normalizeRoute(route), handler);
    return () => routes.delete(normalizeRoute(route));
  }

  function start({ dispatchInitial = true } = {}) {
    if (started) return;
    started = true;
    window.addEventListener("hashchange", dispatch);
    // 入口可先完成共享数据初始化，再显式 dispatch，避免首屏重复加载。
    if (dispatchInitial) dispatch();
  }

  function stop() {
    if (!started) return;
    started = false;
    window.removeEventListener("hashchange", dispatch);
  }

  return { current, navigate, register, start, stop, dispatch };
}
