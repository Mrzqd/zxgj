import { useRef, useState } from 'react';

export function useSubmitting() {
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);

  async function guard(action: () => Promise<void>) {
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      await action();
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  return { submitting, guard };
}
