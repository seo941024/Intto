// 서버와 브라우저가 같이 쓰는 작은 도우미

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

// x로 정렬된 목록에서 x 이상인 첫 칸
export function lowerBound(arr, x) {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if (arr[m].x < x) lo = m + 1;
    else hi = m;
  }
  return lo;
}
