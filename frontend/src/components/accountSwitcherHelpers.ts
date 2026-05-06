export const getAccountColor = (email: string): string => {
    const colors = [
        'from-brand-surface-2 to-brand-surface',
        'from-slate-700 to-brand-surface-2',
        'from-slate-800 to-brand-surface',
    ];
    const hash = email.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
    return colors[hash % colors.length];
};

export const getEmailInitials = (email: string): string => {
    if (!email || email === 'default') return '?';
    const username = email.split('@')[0];
    if (username.length === 1) return username.toUpperCase();
    const parts = username.split(/[._-]/);
    if (parts.length > 1) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return username.substring(0, 2).toUpperCase();
};
