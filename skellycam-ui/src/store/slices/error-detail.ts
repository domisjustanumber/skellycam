// No imports: the node unit test loads this file directly.

/** The reason of a refused request from its JSON body (`detail`: a text, a FastAPI 422 list or an object), else the status text. */
export function errorDetail(body: unknown, statusText: string): string {
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === 'string') return detail || statusText;
    if (detail === undefined || detail === null) return statusText;
    const items = Array.isArray(detail) ? detail : [detail];
    return items.map(item => typeof item?.msg === 'string' ? item.msg : JSON.stringify(item)).join('; ');
}
