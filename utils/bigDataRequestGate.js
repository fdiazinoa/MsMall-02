/**
 * Keeps stale async responses from replacing data after the selected mall
 * changes. Starting a request invalidates every request started before it.
 */
export const createBigDataRequestGate = () => {
  let latestRequest = 0;

  return {
    begin() {
      latestRequest += 1;
      return latestRequest;
    },
    isCurrent(requestId) {
      return requestId === latestRequest;
    },
  };
};
