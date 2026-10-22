export interface Fix {
	lat: number;
	lng: number;
	accuracy: number;
}

/** Great-circle distance in metres (same formula as the API). */
export function distanceM(lat1: number, lng1: number, lat2: number, lng2: number): number {
	const r = (d: number) => (d * Math.PI) / 180;
	const h = Math.sin(r(lat2 - lat1) / 2) ** 2 + Math.cos(r(lat1)) * Math.cos(r(lat2)) * Math.sin(r(lng2 - lng1) / 2) ** 2;
	return 2 * 6371000 * Math.asin(Math.sqrt(h));
}

export function locate(): Promise<Fix> {
	return new Promise((resolve, reject) => {
		if (!('geolocation' in navigator)) {
			reject(new Error('This phone cannot share its location.'));
			return;
		}
		navigator.geolocation.getCurrentPosition(
			(p) => resolve({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy }),
			(e) =>
				reject(
					new Error(
						e.code === 1
							? 'Location is blocked. Allow location for this site in your browser settings, then try again.'
							: 'Could not get your location. Step outside or near a window and try again.'
					)
				),
			{ enableHighAccuracy: true, timeout: 20000, maximumAge: 10000 }
		);
	});
}
