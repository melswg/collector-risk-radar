/** A response may update the view only while its request is the latest. */
export function createLatestRequest() {
  let version = 0;
  return () => {
    const request = ++version;
    return () => request === version;
  };
}
