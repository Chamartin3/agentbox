import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import RatingStars from '../src/components/RatingStars';
import * as versionsApi from '../src/api/versions';

vi.mock('../src/api/versions');

describe('RatingStars', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders 5 stars', () => {
    render(
      <RatingStars
        versionId="v1"
        initialRating={null}
      />
    );
    const stars = screen.getAllByRole('button');
    expect(stars).toHaveLength(5);
  });

  it('displays initial rating', () => {
    render(
      <RatingStars
        versionId="v1"
        initialRating={3}
      />
    );
    const stars = screen.getAllByRole('button');
    expect(stars[0].className).toContain('filled');
    expect(stars[2].className).toContain('filled');
    expect(stars[3].className).toContain('empty');
  });

  it('sets rating when star is clicked', async () => {
    (versionsApi.versionsApi.setRating as any).mockResolvedValue({ rating: 4 });

    const onRatingChange = vi.fn();
    render(
      <RatingStars
        versionId="v1"
        initialRating={null}
        onRatingChange={onRatingChange}
      />
    );

    const stars = screen.getAllByRole('button');
    fireEvent.click(stars[3]); // Click 4th star

    expect(versionsApi.versionsApi.setRating).toHaveBeenCalledWith('v1', 4);

    await waitFor(() => {
      expect(onRatingChange).toHaveBeenCalledWith(4);
    });
  });

  it('clears rating when same star is clicked again', async () => {
    (versionsApi.versionsApi.clearRating as any).mockResolvedValue(undefined);

    const onRatingChange = vi.fn();
    render(
      <RatingStars
        versionId="v1"
        initialRating={3}
        onRatingChange={onRatingChange}
      />
    );

    const stars = screen.getAllByRole('button');
    fireEvent.click(stars[2]); // Click 3rd star again

    expect(versionsApi.versionsApi.clearRating).toHaveBeenCalledWith('v1');
  });

  it('shows hover preview', () => {
    render(
      <RatingStars
        versionId="v1"
        initialRating={2}
      />
    );

    const stars = screen.getAllByRole('button');
    fireEvent.mouseEnter(stars[4]); // Hover 5th star

    // All 5 stars should appear filled during hover
    const allFilled = stars.every(s => s.className.includes('filled'));
    expect(allFilled).toBe(true);

    fireEvent.mouseLeave(stars[4]);
    // Back to original rating
    const originalState = stars[2].className.includes('filled');
    expect(originalState).toBe(true);
  });

  it('is disabled when readOnly is true', () => {
    render(
      <RatingStars
        versionId="v1"
        initialRating={3}
        readOnly={true}
      />
    );

    const stars = screen.getAllByRole('button');
    stars.forEach(star => {
      expect(star).toBeDisabled();
    });
  });
});
