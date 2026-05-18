import { describe, it, expect, vi, beforeEach } from 'vitest';

const { mockGet } = vi.hoisted(() => ({
  mockGet: vi.fn(),
}));

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>();
  return {
    ...actual,
    default: {
      ...actual.default,
      create: () => ({
        get: mockGet,
        post: vi.fn(),
        interceptors: { response: { use: vi.fn() } },
      }),
    },
    isAxiosError: actual.isAxiosError,
  };
});

import { apiService } from '../api';

describe('apiService.searchEmails', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockGet.mockResolvedValue({ data: [] });
  });

  it('includes has_attachments param when provided as true', async () => {
    await apiService.searchEmails('invoice', 'acc1', 'en', 50, true);
    const [, config] = mockGet.mock.calls[0];
    expect(config.params.has_attachments).toBe(true);
  });

  it('includes has_attachments param when provided as false', async () => {
    await apiService.searchEmails('invoice', 'acc1', 'en', 50, false);
    const [, config] = mockGet.mock.calls[0];
    expect(config.params.has_attachments).toBe(false);
  });

  it('omits has_attachments param when undefined', async () => {
    await apiService.searchEmails('invoice', 'acc1', 'en', 50, undefined);
    const [, config] = mockGet.mock.calls[0];
    expect(config.params).not.toHaveProperty('has_attachments');
  });
});
