// cppring_py.cpp - the C++ ring (ring.hpp) exposed to Python (NOT SkellyCam code): the "hybrid" option.
//
// Built as cppring.cp312-win_amd64.pyd by ../build.bat, against the .venv-bench pybind11 headers and the uv CPython 3.12.
// Two access paths to the SAME native functions:
//   * pybind11 class Ring: publish()/read() take any buffer-protocol object (numpy array) WITHOUT copying it
//     (py::buffer -> raw pointer), and release the GIL around the memcpy.
//   * plain C exports cr_publish / cr_read / cr_can_write (callable through ctypes), to compare binding overheads.
#include "ring.hpp"
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>

namespace py = pybind11;
using namespace cr;

extern "C" {
__declspec(dllexport) void cr_publish(uint8_t* base, int64_t L, int64_t rb, int64_t stride, int64_t k, const uint8_t* src) {
    Ring r; r.spec.L = L; r.spec.record_bytes = rb; r.spec.stride = stride; r.base = base; r.publish(k, src);
}
__declspec(dllexport) int cr_read(uint8_t* base, int64_t L, int64_t rb, int64_t stride, int64_t k, uint8_t* dst) {
    Ring r; r.spec.L = L; r.spec.record_bytes = rb; r.spec.stride = stride; r.base = base; return r.read(k, dst);
}
__declspec(dllexport) int cr_can_write(uint8_t* base, int64_t L, int64_t k) {
    return reinterpret_cast<std::atomic<int64_t>*>(base + 64)->load(std::memory_order_acquire) >= k - L ? 1 : 0;
}
__declspec(dllexport) void cr_noop() {}
}

struct PyRing {
    Mapping m; Ring r; std::wstring name; bool owner;
    PyRing(const std::string& nm, int64_t h, int64_t w, bool aligned, bool create) : owner(create) {
        name = std::wstring(nm.begin(), nm.end());
        r.spec = make_spec(h, w, aligned);
        m = create ? Mapping::create(name, r.spec.total_bytes()) : Mapping::open(name, r.spec.total_bytes());
        r.base = m.base;
        if (create) r.init();
    }
    static const uint8_t* ptr_of(const py::buffer& b, int64_t need, bool writable) {
        py::buffer_info bi = b.request(writable);
        if (bi.size * bi.itemsize < need) throw std::runtime_error("buffer too small");
        return (const uint8_t*)bi.ptr;
    }
    void publish(int64_t k, const py::buffer& src) {
        const uint8_t* p = ptr_of(src, r.spec.record_bytes, false);
        py::gil_scoped_release nogil;
        r.publish(k, p);
    }
    void publish_gil(int64_t k, const py::buffer& src) {  // same, GIL held (to measure the release cost)
        r.publish(k, ptr_of(src, r.spec.record_bytes, false));
    }
    int read(int64_t k, py::buffer& dst) {
        uint8_t* p = (uint8_t*)ptr_of(dst, r.spec.record_bytes, true);
        py::gil_scoped_release nogil;
        return r.read(k, p);
    }
    void wait_can_write(int64_t k) {  // native wait loop, Sleep(0) per failed poll (same policy as every implementation)
        py::gil_scoped_release nogil;
        while (!r.can_write(k)) Sleep(0);
    }
    py::memoryview slot_view(int64_t i) {  // zero-copy view of one slot's record bytes
        return py::memoryview::from_memory(r.slot(i % r.spec.L), (py::ssize_t)r.spec.record_bytes, false);
    }
    void close() { m.close(); }
};

PYBIND11_MODULE(cppring, mod) {
    mod.doc() = "C++ seqlock SPSC frame ring over a named Win32 file mapping (benchmark prototype)";
    py::class_<PyRing>(mod, "Ring")
        .def(py::init<const std::string&, int64_t, int64_t, bool, bool>(), py::arg("name"), py::arg("h"), py::arg("w"),
             py::arg("aligned") = true, py::arg("create") = false)
        .def("publish", &PyRing::publish)
        .def("publish_gil", &PyRing::publish_gil)
        .def("read", &PyRing::read)
        .def("wait_can_write", &PyRing::wait_can_write)
        .def("can_write", [](PyRing& s, int64_t k) { return s.r.can_write(k); })
        .def("head", [](PyRing& s) { return s.r.head()->load(std::memory_order_acquire); })
        .def("cursor", [](PyRing& s) { return s.r.cursor()->load(std::memory_order_acquire); })
        .def("set_cursor", [](PyRing& s, int64_t k) { s.r.cursor()->store(k, std::memory_order_release); })
        .def("done", [](PyRing& s) { return s.r.done()->load(std::memory_order_acquire); })
        .def("set_done", [](PyRing& s, int64_t k) { s.r.done()->store(k, std::memory_order_release); })
        .def("slot_view", &PyRing::slot_view)
        .def("noop", [](PyRing&) {})
        .def("close", &PyRing::close)
        .def_property_readonly("L", [](PyRing& s) { return s.r.spec.L; })
        .def_property_readonly("record_bytes", [](PyRing& s) { return s.r.spec.record_bytes; })
        .def_property_readonly("stride", [](PyRing& s) { return s.r.spec.stride; })
        .def_property_readonly("base_addr", [](PyRing& s) { return (uintptr_t)s.r.base; });
}
