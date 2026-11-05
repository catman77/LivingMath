// Same WhiteStar/CAD/UDAV transition rule as source.py. C++17, no fast-math.
// The selected-observation graph is a walk, hence connected after step one.
// Thus a new edge closes a cycle iff its destination is already visited.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <new>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr int NSIG = 7 * 3 * 4 * 3 * 3 * 8;
constexpr std::uint64_t MAX_STEPS = (1ULL << 48);
constexpr double PI = 3.141592653589793238462643383279502884;
using Matrix = std::array<std::int64_t, 4>;
thread_local std::string error_message;

std::int64_t mod(std::int64_t value, std::int64_t modulus) {
    auto r = value % modulus;
    return r < 0 ? r + modulus : r;
}

struct Projection {
    std::int64_t x, y;
    int signature, phase, depth;
};

Projection project(const Matrix& m, std::int64_t a, std::int64_t b) {
    // ws_run preflights a conservative bound before mutating any state.
    const auto x = m[0] * a + m[1] * b;
    const auto y = m[2] * a + m[3] * b;
    auto aa = x < 0 ? -x : x, bb = y < 0 ? -y : y;
    int depth = 0, odd = 0;
    while (bb != 0) {
        auto q = aa / bb, r = aa % bb;
        odd += static_cast<int>(q & 1);
        ++depth;
        aa = bb; bb = r;
    }
    const double theta = (x || y) ? std::atan2(static_cast<double>(y), static_cast<double>(x)) : 0.0;
    double u = std::fmod(theta / (PI / 2.0), 1.0);
    if (u < 0.0) u += 1.0; // Python's positive-divisor remainder.
    u = std::min(std::max(u, 1e-12), 1.0 - 1e-12);
    const int phase = std::min(static_cast<int>(u * 8.0), 7);
    const int sx = (x > 0) - (x < 0), sy = (y > 0) - (y < 0);
    int id = std::min(depth, 6);
    id = id * 3 + odd % 3;
    id = id * 4 + static_cast<int>(std::min<std::int64_t>(aa, 3));
    id = id * 3 + sx + 1;
    id = id * 3 + sy + 1;
    id = id * 8 + phase;
    return {x, y, id, phase, depth};
}

struct Engine {
    std::int64_t seed;
    int k, mode, chart_stride = 11, previous = -1;
    unsigned ra, rb;
    std::uint64_t steps = 0, projections = 0, vertices = 0, edge_count = 0;
    std::int64_t layer = 0, position = 0, witness_stride;
    std::uint64_t max_coefficient = 0;
    std::vector<Matrix> charts;
    std::vector<std::uint64_t> used;
    std::array<std::uint64_t, NSIG> seen{};
    std::array<std::uint64_t, 8> phase{};
    std::vector<std::uint64_t> edges;

    Engine(std::int64_t value, int candidates, int fixed, const std::int64_t* matrices, int n)
        : seed(value), k(candidates), mode(fixed),
          ra(static_cast<std::uint64_t>(value) & 255),
          rb(((static_cast<std::uint64_t>(value) & 255) * 73 + 37) & 255),
          witness_stride(2 * mod(value, 19) + 1),
          edges((std::uint64_t(NSIG) * (NSIG - 1) / 2 + 63) / 64, 0) {
        if (mode != 0 && mode != 1) throw std::invalid_argument("invalid mode");
        set_charts(matrices, n);
    }

    void set_charts(const std::int64_t* matrices, int n) {
        if (n < 1 || n > 4096 || k < 1 || k > n)
            throw std::invalid_argument("require 1 <= k <= number of charts <= 4096");
        std::vector<Matrix> next;
        std::vector<std::uint64_t> counts(n, 0);
        std::uint64_t limit = 0;
        for (int j = 0; j < n; ++j) {
            Matrix m{matrices[4*j], matrices[4*j+1], matrices[4*j+2], matrices[4*j+3]};
            // Coefficients are bounded below 2^62; determinant fits __int128.
            for (auto c : m) {
                if (c <= -(1LL << 61) || c >= (1LL << 61))
                    throw std::invalid_argument("CAD coefficient outside native exact-integer range");
                limit = std::max(limit, std::uint64_t(c < 0 ? -c : c));
            }
            if (__int128(m[0]) * m[3] - __int128(m[1]) * m[2] == 0)
                throw std::invalid_argument("singular CAD matrix");
            if (std::find(next.begin(), next.end(), m) != next.end())
                throw std::invalid_argument("duplicate CAD matrix");
            auto old = std::find(charts.begin(), charts.end(), m);
            if (old != charts.end()) counts[j] = used[old - charts.begin()];
            next.push_back(m);
        }
        charts = std::move(next); used = std::move(counts); max_coefficient = limit;
        chart_stride = 11;
        while (std::gcd(chart_stride, n) != 1) ++chart_stride;
    }

    static std::uint64_t edge_key(int a, int b) {
        if (a > b) std::swap(a, b);
        return std::uint64_t(b) * (b - 1) / 2 + a;
    }
    bool has_edge(int a, int b) const {
        auto key = edge_key(a, b);
        return (edges[key >> 6] >> (key & 63)) & 1;
    }
    void add_edge(int a, int b) {
        auto key = edge_key(a, b);
        edges[key >> 6] |= 1ULL << (key & 63);
        ++edge_count;
    }

    void run(std::uint64_t count, std::uint8_t* states, std::int32_t* views, std::int64_t* audit) {
        if (count > MAX_STEPS - steps) throw std::overflow_error("maximum stream length is 2^48");
        // layer grows by at most count. The sqrt bound is tighter for large batches.
        const auto upper_layer = static_cast<std::uint64_t>(std::sqrt(2.0L * (steps + count))) + 2;
        if (__int128(max_coefficient) * upper_layer >= (1LL << 61))
            throw std::overflow_error("projected coordinates exceed native safe range");
        const int nc = static_cast<int>(charts.size()), candidates = mode ? 1 : k;
        for (std::uint64_t t = 0; t < count; ++t) {
            const auto m = layer + 1;
            const auto a = (position * witness_stride + mod(seed, m)) % m, b = layer - a;
            const auto next_rb = ra ^ (((rb << 1) ^ (rb >> 3)) & 127);
            ra = rb; rb = next_rb;
            const int first = static_cast<int>((rb + ((steps + 1) % nc) * 7 + mod(seed, nc)) % nc);
            int best_view = -1, best_novelty = -1;
            std::uint64_t best_seen = 0, best_phase = 0, best_used = 0;
            Projection best{};
            auto* row = audit ? audit + t * (7 + 5 * candidates) : nullptr;
            for (int c = 0; c < candidates; ++c) {
                const int view = mode ? 0 : (first + c * chart_stride) % nc;
                const auto p = project(charts[view], a, b);
                const bool nv = seen[p.signature] == 0;
                const bool ne = previous >= 0 && previous != p.signature && !has_edge(previous, p.signature);
                const bool cycle = ne && !nv;
                const int novelty = std::min(13, 6 * int(nv) + 3 * int(ne) + 4 * int(cycle));
                const auto visits = seen[p.signature], phases = phase[p.phase], uses = used[view];
                if (row) {
                    auto* r = row + 7 + 5 * c;
                    r[0] = view; r[1] = novelty; r[2] = visits; r[3] = phases; r[4] = uses;
                }
                const bool better = best_view < 0 || novelty > best_novelty ||
                    (novelty == best_novelty && (visits < best_seen ||
                    (visits == best_seen && (phases < best_phase ||
                    (phases == best_phase && uses < best_used)))));
                if (better) {
                    best_view = view; best_novelty = novelty; best = p;
                    best_seen = visits; best_phase = phases; best_used = uses;
                }
            }
            if (!seen[best.signature]) ++vertices;
            if (previous >= 0 && previous != best.signature && !has_edge(previous, best.signature))
                add_edge(previous, best.signature);
            previous = best.signature;
            ++seen[best.signature]; ++phase[best.phase]; ++used[best_view];
            states[t] = (a || b) ? std::min(best.depth, 4) * 8 + best.phase : 40;
            views[t] = best_view;
            if (row) {
                row[0] = steps; row[1] = a; row[2] = b; row[3] = best_view;
                row[4] = best.x; row[5] = best.y; row[6] = best.signature;
            }
            ++steps; projections += candidates;
            if (++position == m) {
                ++layer; position = 0; witness_stride = 2 * mod(seed, 19) + 1;
                while (std::gcd(witness_stride, layer + 1) != 1) witness_stride += 2;
            }
        }
    }
};
} // namespace

extern "C" {
const char* ws_error() { return error_message.c_str(); }
void* ws_create(std::int64_t seed, int k, int mode, const std::int64_t* matrices, int n) {
    try { return new Engine(seed, k, mode, matrices, n); }
    catch (const std::exception& e) { error_message = e.what(); return nullptr; }
}
void ws_destroy(void* handle) { delete static_cast<Engine*>(handle); }
int ws_run(void* handle, std::uint64_t count, std::uint8_t* states, std::int32_t* views, std::int64_t* audit) {
    try { static_cast<Engine*>(handle)->run(count, states, views, audit); return 0; }
    catch (const std::exception& e) { error_message = e.what(); return -1; }
}
int ws_set_charts(void* handle, const std::int64_t* matrices, int n) {
    try { static_cast<Engine*>(handle)->set_charts(matrices, n); return 0; }
    catch (const std::exception& e) { error_message = e.what(); return -1; }
}
void ws_snapshot(void* handle, std::uint64_t* out) {
    auto& s = *static_cast<Engine*>(handle);
    out[0] = s.steps; out[1] = s.projections;
    out[2] = std::count_if(s.used.begin(), s.used.end(), [](auto n) { return n > 0; });
    out[3] = s.charts.size(); out[4] = s.vertices; out[5] = s.edge_count;
    out[6] = s.edges.size() * sizeof(std::uint64_t) + sizeof(s.seen) + sizeof(s.phase);
}
}
