/** 通用弹窗控制器：业务模块只负责填充内容和提交逻辑。 */
export function createModal({ root = "#modal", title = "#modal-title", form = "#modal-form", save = "#btn-modal-save", cancel = "#btn-modal-cancel", close = "#btn-modal-close" } = {}) {
  const element = document.querySelector(root);
  const titleElement = document.querySelector(title);
  const formElement = document.querySelector(form);
  const saveElement = document.querySelector(save);
  let submitHandler = null;
  const closeModal = () => { element.classList.add("hidden"); submitHandler = null; element.dispatchEvent(new CustomEvent("modal:closed")); };
  const openModal = ({ heading, content = "", showSave = true, saveLabel = "保存", onSave = null } = {}) => {
    titleElement.textContent = heading || "";
    formElement.innerHTML = content;
    saveElement.style.display = showSave ? "" : "none";
    saveElement.textContent = saveLabel;
    submitHandler = onSave;
    element.classList.remove("hidden");
  };
  saveElement.addEventListener("click", async () => {
    if (!submitHandler) return;
    saveElement.disabled = true;
    try { await submitHandler(formElement); } finally { saveElement.disabled = false; }
  });
  document.querySelector(cancel)?.addEventListener("click", closeModal);
  document.querySelector(close)?.addEventListener("click", closeModal);
  element.addEventListener("click", event => { if (event.target === element) closeModal(); });
  return { root: element, form: formElement, save: saveElement, open: openModal, close: closeModal };
}
