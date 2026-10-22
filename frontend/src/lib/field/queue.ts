// Photos wait here until they upload: survives signal drops, reloads and a closed browser.

export interface QueuedPhoto {
	ref: string; // unique per photo; the API uses it to make retries safe
	visitId: number;
	blob: Blob;
	lat: number;
	lng: number;
	takenAt: string;
	caption: string;
	state: 'queued' | 'failed';
	error?: string;
}

const DB = 'afe-field';
const STORE = 'uploads';

function open(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const req = indexedDB.open(DB, 1);
		req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'ref' });
		req.onsuccess = () => resolve(req.result);
		req.onerror = () => reject(req.error);
	});
}

async function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T> | void): Promise<T | undefined> {
	const db = await open();
	return new Promise((resolve, reject) => {
		const tx = db.transaction(STORE, mode);
		const req = fn(tx.objectStore(STORE));
		tx.oncomplete = () => resolve(req ? req.result : undefined);
		tx.onerror = () => reject(tx.error);
	});
}

export const putPhoto = (item: QueuedPhoto) => run('readwrite', (s) => s.put(item));
export const deletePhoto = (ref: string) => run('readwrite', (s) => s.delete(ref));
export async function photosFor(visitId: number): Promise<QueuedPhoto[]> {
	const all = ((await run<QueuedPhoto[]>('readonly', (s) => s.getAll() as IDBRequest<QueuedPhoto[]>)) ?? []) as QueuedPhoto[];
	return all.filter((p) => p.visitId === visitId);
}

export function newRef(): string {
	return crypto.randomUUID ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Shrink before upload: about 250 KB instead of 4 MB on paid mobile data. The API
 * re-encodes and strips metadata again, so this only saves data. */
export async function shrink(file: File, maxEdge = 1600, quality = 0.85): Promise<Blob> {
	try {
		const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
		const scale = Math.min(1, maxEdge / Math.max(bmp.width, bmp.height));
		const canvas = document.createElement('canvas');
		canvas.width = Math.round(bmp.width * scale);
		canvas.height = Math.round(bmp.height * scale);
		canvas.getContext('2d')!.drawImage(bmp, 0, 0, canvas.width, canvas.height);
		bmp.close();
		const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', quality));
		return blob && blob.size < file.size ? blob : file;
	} catch {
		return file;
	}
}
