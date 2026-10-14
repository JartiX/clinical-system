// Низкоуровневые запросы к API: разбор ошибок FastAPI в читаемый текст

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function parse<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
  let message = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") message = body.detail;
    else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // тело не JSON — оставляем статус
  }
  throw new ApiError(response.status, message);
}

export const http = {
  get: <T>(url: string) => fetch(url).then(parse<T>),
  post: <T>(url: string, body: unknown) =>
    fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(
      parse<T>,
    ),
  patch: <T>(url: string, body: unknown) =>
    fetch(url, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(
      parse<T>,
    ),
  postForm: <T>(url: string, form: FormData) => fetch(url, { method: "POST", body: form }).then(parse<T>),
};

export const enc = encodeURIComponent;
