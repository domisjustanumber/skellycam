import { useEffect } from 'react';
import { useAppDispatch } from '@/store';
import { hardwareCameraEnumerationChanged } from '@/store/slices/cameras/cameras-slice';

/** Surfaces navigator.mediaDevices 'devicechange' as a Redux hint without blocking the renderer. */
export function useUsbCameraEnumerationListener(): void {
    const dispatch = useAppDispatch();

    useEffect(() => {
        const md = globalThis.navigator?.mediaDevices;
        if (!md || typeof md.addEventListener !== 'function') return;

        const onChange = (): void => {
            dispatch(hardwareCameraEnumerationChanged());
        };
        md.addEventListener('devicechange', onChange);
        return () => md.removeEventListener('devicechange', onChange);
    }, [dispatch]);
}
