/**
 * 前端接口访问层。
 *
 * 模块只负责 HTTP 协议、JSON 编解码和错误标准化，不承担页面加载提示或
 * DOM 更新职责。页面可通过 signal 取消已经失效的查询，避免旧请求覆盖新结果。
 */

export class ApiError extends Error {
  constructor(message, { status = 0, data = null, path = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.path = path;
  }
}

/** 认证失效时由入口文件监听该事件，并切换至登录界面。 */
export const UNAUTHORIZED_EVENT = "project-management:unauthorized";
let unauthorizedHandler = null;

/** 允许入口文件注册登录面板处理器，同时保留事件通知供其他模块监听。 */
export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
  return () => { unauthorizedHandler = null; };
}

function emitUnauthorized(path) {
  unauthorizedHandler?.({ path });
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT, { detail: { path } }));
}

function isJsonResponse(response) {
  return (response.headers.get("content-type") || "").includes("application/json");
}

/**
 * 创建 API 客户端。调用示例：
 * const api = createApiClient();
 * const result = await api.get("/projects", { signal: controller.signal });
 */
export function createApiClient({ baseUrl = "/api", fetchImpl = globalThis.fetch?.bind(globalThis) } = {}) {
  async function request(path, { method = "GET", body, headers = {}, signal } = {}) {
    const requestHeaders = new Headers(headers);
    const options = { method, headers: requestHeaders, signal };

    if (body !== undefined && body !== null) {
      requestHeaders.set("Content-Type", "application/json");
      options.body = JSON.stringify(body);
    }

    if (!fetchImpl) throw new Error("当前环境未提供 fetch API");
    const response = await fetchImpl(`${baseUrl}${path}`, options);
    const data = isJsonResponse(response) ? await response.json() : null;

    if (!response.ok) {
      const message = data?.error || `请求失败(${response.status})`;
      if (response.status === 401 && path !== "/auth/login") emitUnauthorized(path);
      throw new ApiError(message, { status: response.status, data, path });
    }
    return data;
  }

  return {
    request,
    get: (path, options = {}) => request(path, { ...options, method: "GET" }),
    post: (path, body, options = {}) => request(path, { ...options, method: "POST", body }),
    put: (path, body, options = {}) => request(path, { ...options, method: "PUT", body }),
    delete: (path, options = {}) => request(path, { ...options, method: "DELETE" }),
  };
}

export const api = createApiClient();

/**
 * 为同一业务键维护一个最新请求。开始新请求时自动取消旧请求，适合搜索框和分页切换。
 */
export function createLatestRequest() {
  const controllers = new Map();
  return async function latest(key, task) {
    controllers.get(key)?.abort();
    const controller = new AbortController();
    controllers.set(key, controller);
    try {
      return await task(controller.signal);
    } finally {
      if (controllers.get(key) === controller) controllers.delete(key);
    }
  };
}
