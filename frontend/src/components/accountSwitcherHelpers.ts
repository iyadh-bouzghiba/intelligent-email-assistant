export const getAccountColor = (email: string): string => {
    const colors = [
        'from-blue-500 to-indigo-600',
        'from-purple-500 to-pink-600',
        'from-emerald-500 to-teal-600',
        'from-amber-500 to-orange-600',
        'from-rose-500 to-red-600',
        'from-cyan-500 to-blue-600',
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
