const REMEMBER_SAVE_PATH_KEY = 'jav-downloader-remember-save-path';
const SAVE_PATH_KEY = 'jav-downloader-save-path';

export function loadRememberSavePath(): boolean {
  try {
    return localStorage.getItem(REMEMBER_SAVE_PATH_KEY) === '1';
  } catch {
    return false;
  }
}

export function loadSavedPath(): string {
  try {
    return localStorage.getItem(SAVE_PATH_KEY) || '';
  } catch {
    return '';
  }
}

export function persistSavePath(path: string, remember: boolean): void {
  try {
    if (remember && path.trim()) {
      localStorage.setItem(REMEMBER_SAVE_PATH_KEY, '1');
      localStorage.setItem(SAVE_PATH_KEY, path.trim());
      return;
    }
    localStorage.removeItem(REMEMBER_SAVE_PATH_KEY);
    localStorage.removeItem(SAVE_PATH_KEY);
  } catch {
    // ignore quota / private mode
  }
}

export function clearSavedPath(): void {
  persistSavePath('', false);
}
