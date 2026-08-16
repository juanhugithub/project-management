/**
 * 简洁的集中状态容器。
 * 页面状态必须完整保留筛选条件和分页信息，加载失败时清空旧数据，防止界面把过期结果
 * 误呈现为当前筛选条件的结果。
 */

export const PAGE_STATUS = Object.freeze({
  IDLE: "idle",
  LOADING: "loading",
  READY: "ready",
  ERROR: "error",
});

export function createPageState({ data = [], filters = {}, pagination = {} } = {}) {
  return {
    status: PAGE_STATUS.IDLE,
    data,
    error: null,
    filters,
    pagination,
  };
}

/**
 * 状态修改以不可变替换方式提交。订阅者只会在提交后收到最新快照，页面模块据此渲染。
 */
export function createStore(initialState = {}) {
  let state = structuredClone(initialState);
  const listeners = new Set();

  function getState() {
    return state;
  }

  function notify() {
    for (const listener of listeners) listener(state);
  }

  function setState(updater) {
    const nextState = typeof updater === "function" ? updater(state) : updater;
    if (!nextState || typeof nextState !== "object") {
      throw new TypeError("状态更新必须返回对象");
    }
    state = nextState;
    notify();
    return state;
  }

  function patch(patchValue) {
    return setState(current => ({ ...current, ...patchValue }));
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return { getState, setState, patch, subscribe };
}

/** 默认全局状态容器，页面模块可按需继续拆分 pages 字段。 */
export const state = createStore({ pages: {} });

export function setPageStatus(store, pageName, status, patch = {}) {
  return patchPage(store, pageName, { status, ...patch });
}

/** 仅更新一个页面的状态，避免不同业务页面相互覆盖。 */
export function patchPage(store, pageName, patchValue) {
  return store.setState(current => ({
    ...current,
    pages: {
      ...current.pages,
      [pageName]: { ...current.pages?.[pageName], ...patchValue },
    },
  }));
}
