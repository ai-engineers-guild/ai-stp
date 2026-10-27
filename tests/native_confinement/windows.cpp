// Disposable CI experiment, not a provider launcher or a product capability.
// Documented API: learn.microsoft.com/windows/win32/secauthz/implementing-an-appcontainer
#define _WIN32_WINNT 0x0A00
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <userenv.h>
#include <aclapi.h>
#include <sddl.h>
#include <objbase.h>
#include <array>
#include <cstring>
#include <limits>
#include <sstream>
#include <exception>
#include <optional>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace fs = std::filesystem;
struct Failure { const char* stage; DWORD code; };
void require(bool value, const char* stage, DWORD code = 0) {
    if (!value) throw Failure{stage, code};
}
void win(BOOL value, const char* stage) {
    if (!value) throw Failure{stage, GetLastError()};
}
struct Handle {
    HANDLE value = nullptr;
    explicit Handle(HANDLE h = nullptr) : value(h) {}
    ~Handle() { if (value && value != INVALID_HANDLE_VALUE) CloseHandle(value); }
    Handle(const Handle&) = delete;
    Handle& operator=(const Handle&) = delete;
};
struct Local {
    void* value = nullptr;
    ~Local() { if (value) LocalFree(value); }
};
struct Profile {
    std::wstring name;
    PSID sid = nullptr;
    bool created = false;
    ~Profile() {
        if (created) {
            const HRESULT result = DeleteAppContainerProfile(name.c_str());
            if (FAILED(result)) std::cout << "{\"cleanup\":\"profile\",\"native_code\":"
                << static_cast<DWORD>(result) << "}" << std::endl;
        }
        if (sid) FreeSid(sid);
    }
    void close() {
        require(created, "profile_cleanup_ownership");
        const HRESULT result = DeleteAppContainerProfile(name.c_str());
        created = false;
        require(SUCCEEDED(result), "profile_cleanup", static_cast<DWORD>(result));
    }
};
struct Fixture {
    fs::path root;
    bool owned = false;
    ~Fixture() {
        if (owned) { std::error_code ec; fs::remove_all(root, ec); }
    }
    void close() {
        require(owned, "fixture_cleanup_ownership");
        std::error_code ec;
        fs::remove_all(root, ec);
        require(!ec && !fs::exists(root), "fixture_cleanup", static_cast<DWORD>(ec.value()));
        owned = false;
    }
};

void grant(const fs::path& path, PSID sid, DWORD access, DWORD inheritance) {
    Local descriptor, replacement;
    PACL current = nullptr;
    DWORD result = GetNamedSecurityInfoW(path.c_str(), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION, nullptr, nullptr, &current, nullptr, &descriptor.value);
    require(result == ERROR_SUCCESS, "read_owned_acl", result);
    EXPLICIT_ACCESSW rule{};
    rule.grfAccessPermissions = access;
    rule.grfAccessMode = GRANT_ACCESS;
    rule.grfInheritance = inheritance;
    rule.Trustee.TrusteeForm = TRUSTEE_IS_SID;
    rule.Trustee.TrusteeType = TRUSTEE_IS_UNKNOWN;
    rule.Trustee.ptstrName = static_cast<LPWSTR>(sid);
    PACL next = nullptr;
    result = SetEntriesInAclW(1, &rule, current, &next);
    replacement.value = next;
    require(result == ERROR_SUCCESS, "compose_owned_acl", result);
    result = SetNamedSecurityInfoW(const_cast<LPWSTR>(path.c_str()), SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION, nullptr, nullptr, next, nullptr);
    require(result == ERROR_SUCCESS, "write_owned_acl", result);
}
void low_integrity(const fs::path& path) {
    Local descriptor;
    win(ConvertStringSecurityDescriptorToSecurityDescriptorW(L"S:(ML;OICI;NW;;;LW)",
        SDDL_REVISION_1, &descriptor.value, nullptr), "low_label_descriptor");
    BOOL present = FALSE, inherited = FALSE;
    PACL label = nullptr;
    win(GetSecurityDescriptorSacl(descriptor.value, &present, &label, &inherited),
        "low_label_read");
    require(present && label, "low_label_shape");
    const DWORD result = SetNamedSecurityInfoW(const_cast<LPWSTR>(path.c_str()),
        SE_FILE_OBJECT, LABEL_SECURITY_INFORMATION, nullptr, nullptr, nullptr, label);
    require(result == ERROR_SUCCESS, "low_label_apply", result);
}
void write(const fs::path& path, const std::string& bytes) {
    Handle file(CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
        FILE_ATTRIBUTE_NORMAL, nullptr));
    win(file.value != INVALID_HANDLE_VALUE, "owned_write_open");
    DWORD count = 0;
    win(WriteFile(file.value, bytes.data(), static_cast<DWORD>(bytes.size()), &count, nullptr),
        "owned_write");
    require(count == bytes.size(), "owned_write_size");
}
void publish(const fs::path& path, const std::string& bytes) {
    fs::path pending = path;
    pending += L".pending";
    write(pending, bytes);
    win(MoveFileW(pending.c_str(), path.c_str()), "owned_publish");
}
bool denied(const fs::path& path, DWORD access) {
    Handle file(CreateFileW(path.c_str(), access, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    if (file.value != INVALID_HANDLE_VALUE) return false;
    require(GetLastError() == ERROR_ACCESS_DENIED, "refusal_category", GetLastError());
    return true;
}
void readable(const fs::path& path) {
    Handle file(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    win(file.value != INVALID_HANDLE_VALUE, "positive_read_open");
    char value[64]{};
    DWORD count = 0;
    win(ReadFile(file.value, value, sizeof(value), &count, nullptr), "positive_read");
    require(std::string(value, count) == "synthetic fixture\n", "positive_read_bytes");
}
void token(HANDLE process, PSID expected) {
    HANDLE raw = nullptr;
    win(OpenProcessToken(process, TOKEN_QUERY, &raw), "token_open");
    Handle held(raw);
    DWORD count = 0, container = 0;
    win(GetTokenInformation(held.value, TokenIsAppContainer, &container,
        sizeof(container), &count), "token_container");
    require(container != 0, "token_container_value");
    GetTokenInformation(held.value, TokenAppContainerSid, nullptr, 0, &count);
    require(GetLastError() == ERROR_INSUFFICIENT_BUFFER && count <= 4096,
        "token_sid_size");
    std::vector<unsigned char> buffer(count);
    win(GetTokenInformation(held.value, TokenAppContainerSid, buffer.data(), count,
        &count), "token_sid");
    const auto info = reinterpret_cast<TOKEN_APPCONTAINER_INFORMATION*>(buffer.data());
    require(info->TokenAppContainer && EqualSid(info->TokenAppContainer, expected),
        "token_sid_value");
    GetTokenInformation(held.value, TokenCapabilities, nullptr, 0, &count);
    require(GetLastError() == ERROR_INSUFFICIENT_BUFFER && count <= 65536,
        "token_capabilities_size");
    buffer.resize(count);
    win(GetTokenInformation(held.value, TokenCapabilities, buffer.data(), count,
        &count), "token_capabilities");
    require(reinterpret_cast<TOKEN_GROUPS*>(buffer.data())->GroupCount == 0,
        "token_capabilities_empty");
}
std::wstring quote(const std::wstring& text) {
    std::wstring out = L"\"";
    size_t slashes = 0;
    for (wchar_t character : text) {
        if (character == L'\\') { ++slashes; continue; }
        if (character == L'"') out.append(slashes * 2 + 1, L'\\');
        else out.append(slashes, L'\\');
        slashes = 0;
        out += character;
    }
    out.append(slashes * 2, L'\\');
    return out + L'"';
}
constexpr std::array worker_stages{
    "worker_arguments", "worker_sid_parse", "token_open", "token_container",
    "token_container_value", "token_sid_size", "token_sid", "token_sid_value",
    "token_capabilities_size", "token_capabilities", "token_capabilities_empty",
    "worker_job_query", "worker_job_value", "environment_secret_absent",
    "positive_read_open", "positive_read", "positive_read_bytes",
    "refusal_category", "outside_read", "outside_write", "credential_read",
    "lpac_aap_refusal", "owned_write_open", "owned_write", "owned_write_size",
    "descendant_create", "worker_timeout", "worker_status", "worker_exit",
    "descendant_parent_approval", "descendant_resume", "owned_publish",
    "attribute_size", "attribute_initialize", "attribute_capabilities", "attribute_lpac",
    "bootstrap_path", "system_directory",
};
DWORD worker_stage_code(const char* stage) {
    for (size_t index = 0; index < worker_stages.size(); ++index)
        if (std::strcmp(stage, worker_stages[index]) == 0)
            return 1000 + static_cast<DWORD>(index);
    return 1999;
}
struct FailureEvidence {
    fs::path root;
    std::wstring mode;
    ~FailureEvidence() {
        if (std::uncaught_exceptions() == 0) return;
        try {
            for (const auto& role : {L"parent", L"child"}) {
                std::ifstream file(root / L"target" / (mode + L"-" + role + L".failure"),
                    std::ios::binary);
                if (!file) continue;
                char bytes[64]{};
                file.read(bytes, sizeof(bytes));
                if (!file.eof()) continue;
                std::istringstream fields(std::string(bytes, static_cast<size_t>(file.gcount())));
                unsigned long long stage = 0, code = 0, policy_known = 0, child_denied = 0, bootstrap_matches = 0;
                if (!(fields >> stage >> code >> policy_known >> child_denied >> bootstrap_matches)) continue;
                fields >> std::ws;
                if (!fields.eof() || stage < 1000 || stage >= 1000 + worker_stages.size()
                    || code > std::numeric_limits<DWORD>::max()
                    || policy_known > 1 || child_denied > 1 || bootstrap_matches > 1) continue;
                std::cout << "{\"worker_failure_stage\":\"" << worker_stages[stage - 1000]
                    << "\",\"original_native_code\":" << code
                    << ",\"child_policy_observed\":" << policy_known
                    << ",\"child_policy_denies_creation\":" << child_denied
                    << ",\"localappdata_matches_bootstrap\":" << bootstrap_matches
                    << "}" << std::endl;
            }
        } catch (...) {
            std::cout << "{\"diagnostic\":\"worker_failure_evidence_unavailable\"}" << std::endl;
        }
    }
};
void wait_process(HANDLE process) {
    require(WaitForSingleObject(process, 15000) == WAIT_OBJECT_0, "worker_timeout");
    DWORD status = 0;
    win(GetExitCodeProcess(process, &status), "worker_status");
    if (status >= 1000 && status < 1000 + worker_stages.size()) {
        std::cout << "{\"worker_failure_stage\":\"" << worker_stages[status - 1000]
            << "\"}" << std::endl;
    }
    if (status >= 1000 && status < 1000 + worker_stages.size())
        throw Failure{worker_stages[status - 1000], status};
    require(status == 0, "worker_exit", status);
}
void wait_file(const fs::path& path, const char* stage, HANDLE process = nullptr) {
    for (int observation = 0; observation < 1000; ++observation) {
        if (GetFileAttributesW(path.c_str()) != INVALID_FILE_ATTRIBUTES) return;
        require(GetLastError() == ERROR_FILE_NOT_FOUND, stage, GetLastError());
        if (process && WaitForSingleObject(process, 0) == WAIT_OBJECT_0) {
            wait_process(process);
            throw Failure{stage, 0};
        }
        Sleep(10);
    }
    throw Failure{stage, WAIT_TIMEOUT};
}
DWORD descendant_pid(const fs::path& path) {
    Handle file(CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr));
    win(file.value != INVALID_HANDLE_VALUE, "descendant_pid_open");
    char bytes[16]{};
    DWORD count = 0;
    win(ReadFile(file.value, bytes, sizeof(bytes), &count, nullptr), "descendant_pid_read");
    require(count >= 2 && count <= 11 && bytes[count - 1] == '\n', "descendant_pid_shape");
    unsigned long long pid = 0;
    for (DWORD index = 0; index + 1 < count; ++index) {
        require(bytes[index] >= '0' && bytes[index] <= '9', "descendant_pid_shape");
        pid = pid * 10 + static_cast<unsigned>(bytes[index] - '0');
    }
    require(pid > 0 && pid <= std::numeric_limits<DWORD>::max(), "descendant_pid_range");
    return static_cast<DWORD>(pid);
}
std::wstring environment_block(const fs::path& root, const std::wstring& bootstrap) {
    require(fs::path(bootstrap).is_absolute(), "bootstrap_path");
    wchar_t system[MAX_PATH]{};
    const UINT length = GetWindowsDirectoryW(system, MAX_PATH);
    require(length > 0 && length < MAX_PATH, "system_directory");
    // Windows reroutes LOCALAPPDATA inside a container. Each new launch needs
    // the original verified profile-resolution input, never that rerouted path.
    std::wstring environment = L"LOCALAPPDATA=" + bootstrap;
    environment.push_back(L'\0');
    environment += L"SystemRoot=" + std::wstring(system);
    environment.push_back(L'\0');
    environment += L"TEMP=" + (root / L"target").wstring();
    environment.push_back(L'\0');
    environment += L"TMP=" + (root / L"target").wstring();
    environment.append(2, L'\0');
    return environment;
}
// Explicitly request the same documented LPAC/SID with no extra capabilities
// for its descendant; parent verification and AAP refusal remain mandatory.
struct ContainerAttributes {
    std::vector<unsigned char> storage;
    LPPROC_THREAD_ATTRIBUTE_LIST list = nullptr;
    SECURITY_CAPABILITIES capabilities{};
    DWORD policy = PROCESS_CREATION_ALL_APPLICATION_PACKAGES_OPT_OUT;
    ContainerAttributes(PSID sid, bool lpac) {
        SIZE_T size = 0;
        const DWORD count = lpac ? 2 : 1;
        InitializeProcThreadAttributeList(nullptr, count, 0, &size);
        require(GetLastError() == ERROR_INSUFFICIENT_BUFFER && size <= 65536,
            "attribute_size");
        storage.resize(size);
        list = reinterpret_cast<LPPROC_THREAD_ATTRIBUTE_LIST>(storage.data());
        win(InitializeProcThreadAttributeList(list, count, 0, &size), "attribute_initialize");
        capabilities.AppContainerSid = sid;
        try {
            win(UpdateProcThreadAttribute(list, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                &capabilities, sizeof(capabilities), nullptr, nullptr), "attribute_capabilities");
            if (lpac) win(UpdateProcThreadAttribute(list, 0,
                PROC_THREAD_ATTRIBUTE_ALL_APPLICATION_PACKAGES_POLICY, &policy, sizeof(policy),
                nullptr, nullptr), "attribute_lpac");
        } catch (...) {
            DeleteProcThreadAttributeList(list);
            list = nullptr;
            throw;
        }
    }
    ~ContainerAttributes() { if (list) DeleteProcThreadAttributeList(list); }
    ContainerAttributes(const ContainerAttributes&) = delete;
    ContainerAttributes& operator=(const ContainerAttributes&) = delete;
};
// Grant only a newly named desktop, never change the caller's existing desktop
// or window-station ACL. The package SID cannot switch desktops under the job.
struct PrivateDesktop {
    HDESK value = nullptr;
    std::wstring full_name;
    PrivateDesktop(PSID package, const std::wstring& name) {
        HANDLE raw = nullptr;
        win(OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &raw), "desktop_owner_token");
        Handle held(raw);
        DWORD count = 0;
        GetTokenInformation(held.value, TokenUser, nullptr, 0, &count);
        require(GetLastError() == ERROR_INSUFFICIENT_BUFFER && count <= 65536,
            "desktop_owner_size");
        std::vector<unsigned char> bytes(count);
        win(GetTokenInformation(held.value, TokenUser, bytes.data(), count, &count),
            "desktop_owner");
        Local user_text, package_text, descriptor;
        win(ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER*>(bytes.data())->User.Sid,
            reinterpret_cast<LPWSTR*>(&user_text.value)), "desktop_owner_sid");
        win(ConvertSidToStringSidW(package, reinterpret_cast<LPWSTR*>(&package_text.value)),
            "desktop_package_sid");
        const DWORD rights = READ_CONTROL | DESKTOP_READOBJECTS | DESKTOP_WRITEOBJECTS
            | DESKTOP_CREATEWINDOW | DESKTOP_CREATEMENU;
        std::wostringstream mask;
        mask << L"0x" << std::hex << rights;
        const std::wstring sddl = L"D:P(A;;GA;;;SY)(A;;GA;;;"
            + std::wstring(static_cast<LPCWSTR>(user_text.value)) + L")(A;;"
            + mask.str() + L";;;" + std::wstring(static_cast<LPCWSTR>(package_text.value))
            + L")S:(ML;;NW;;;LW)";
        win(ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl.c_str(),
            SDDL_REVISION_1, &descriptor.value, nullptr), "desktop_descriptor");
        const HWINSTA station = GetProcessWindowStation();
        require(station != nullptr, "desktop_station");
        GetUserObjectInformationW(station, UOI_NAME, nullptr, 0, &count);
        require(GetLastError() == ERROR_INSUFFICIENT_BUFFER && count <= 65536,
            "desktop_station_name_size");
        std::vector<wchar_t> station_name(count / sizeof(wchar_t) + 1, L'\0');
        win(GetUserObjectInformationW(station, UOI_NAME, station_name.data(), count, &count),
            "desktop_station_name");
        full_name = std::wstring(station_name.data()) + L"\\" + name;
        const HDESK original = GetThreadDesktop(GetCurrentThreadId());
        require(original != nullptr, "desktop_original");
        SECURITY_ATTRIBUTES security{sizeof(SECURITY_ATTRIBUTES), descriptor.value, FALSE};
        value = CreateDesktopW(name.c_str(), nullptr, nullptr, 0, rights, &security);
        win(value != nullptr, "desktop_create");
        try {
            win(SetThreadDesktop(original), "desktop_restore");
            Local actual;
            PACL acl = nullptr;
            const DWORD result = GetSecurityInfo(value, SE_WINDOW_OBJECT, DACL_SECURITY_INFORMATION,
                nullptr, nullptr, &acl, nullptr, &actual.value);
            require(result == ERROR_SUCCESS && acl && acl->AceCount == 3,
                "desktop_owned_acl", result);
            bool matched = false;
            for (DWORD index = 0; index < acl->AceCount; ++index) {
                void* raw_ace = nullptr;
                win(GetAce(acl, index, &raw_ace), "desktop_owned_ace");
                const auto ace = static_cast<ACCESS_ALLOWED_ACE*>(raw_ace);
                if (ace->Header.AceType == ACCESS_ALLOWED_ACE_TYPE
                    && EqualSid(&ace->SidStart, package) && ace->Mask == rights) matched = true;
            }
            require(matched, "desktop_owned_package");
        } catch (...) {
            SetThreadDesktop(original);
            CloseDesktop(value);
            value = nullptr;
            throw;
        }
    }
    ~PrivateDesktop() {
        if (value && !CloseDesktop(value)) std::cout
            << "{\"cleanup\":\"desktop\",\"native_code\":" << GetLastError() << "}" << std::endl;
    }
    void close() {
        win(CloseDesktop(value), "desktop_cleanup");
        value = nullptr;
    }
    PrivateDesktop(const PrivateDesktop&) = delete;
    PrivateDesktop& operator=(const PrivateDesktop&) = delete;
};
int worker(int argc, wchar_t** argv) {
    require(argc == 8, "worker_arguments");
    require((std::wstring(argv[2]) == L"lpac" || std::wstring(argv[2]) == L"regular")
        && (std::wstring(argv[3]) == L"parent" || std::wstring(argv[3]) == L"child"),
        "worker_arguments");
    const bool lpac = std::wstring(argv[2]) == L"lpac";
    const bool child = std::wstring(argv[3]) == L"child";
    const fs::path root(argv[4]);
    Local sid;
    win(ConvertStringSidToSidW(argv[5], &sid.value), "worker_sid_parse");
    token(GetCurrentProcess(), sid.value);
    BOOL in_job = FALSE;
    win(IsProcessInJob(GetCurrentProcess(), nullptr, &in_job), "worker_job_query");
    require(in_job, "worker_job_value");
    require(GetEnvironmentVariableW(L"AI_STP_PROBE_PARENT_SECRET", nullptr, 0) == 0,
        "environment_secret_absent");
    readable(root / L"read" / L"canary");
    require(denied(root / L"outside" / L"canary", GENERIC_READ), "outside_read");
    require(denied(root / L"outside" / L"canary", GENERIC_WRITE), "outside_write");
    require(denied(root / L"outside" / L"credentials", GENERIC_READ), "credential_read");
    if (lpac) require(denied(root / L"aap" / L"canary", GENERIC_READ), "lpac_aap_refusal");
    else readable(root / L"aap" / L"canary");
    const std::wstring label = std::wstring(argv[2]) + L"-" + argv[3];
    write(root / L"target" / (label + L".written"), "synthetic fixture\n");
    if (!child) {
        std::wstring command = quote(argv[6]) + L" --worker " + argv[2]
            + L" child " + quote(root.wstring()) + L" " + quote(argv[5])
            + L" " + quote(argv[6]) + L" " + quote(argv[7]);
        STARTUPINFOEXW start{};
        std::optional<ContainerAttributes> attributes;
        if (lpac) {
            attributes.emplace(sid.value, true);
            start.lpAttributeList = attributes->list;
        }
        start.StartupInfo.cb = static_cast<DWORD>(lpac ? sizeof(start) : sizeof(start.StartupInfo));
        auto environment = environment_block(root, argv[7]);
        PROCESS_INFORMATION process{};
        win(CreateProcessW(argv[6], command.data(), nullptr, nullptr, FALSE,
            DETACHED_PROCESS | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
                | (lpac ? EXTENDED_STARTUPINFO_PRESENT : 0),
            environment.data(), (root / L"target").c_str(), &start.StartupInfo, &process),
            "descendant_create");
        Handle held(process.hProcess), thread(process.hThread);
        struct SuspendedChild {
            HANDLE process;
            bool resumed = false;
            ~SuspendedChild() {
                if (!resumed) {
                    TerminateProcess(process, 1);
                    WaitForSingleObject(process, 5000);
                }
            }
        } suspended{held.value};
        publish(root / L"target" / (std::wstring(argv[2]) + L"-descendant.pid"),
            std::to_string(process.dwProcessId) + "\n");
        const auto approval = root / L"read" / (std::wstring(argv[2]) + L"-descendant-approved");
        wait_file(approval, "descendant_parent_approval");
        readable(approval);
        require(ResumeThread(thread.value) != static_cast<DWORD>(-1), "descendant_resume");
        suspended.resumed = true;
        wait_process(held.value);
    }
    return 0;
}
void run(const fs::path& executable, const fs::path& root, PSID sid, bool lpac,
    std::wstring& desktop) {
    FailureEvidence evidence{root, lpac ? L"lpac" : L"regular"};
    struct OwnedJob {
        HANDLE value = CreateJobObjectW(nullptr, nullptr);
        ~OwnedJob() {
            if (!value) return;
            TerminateJobObject(value, 1);
            for (int attempt = 0; attempt < 200; ++attempt) {
                JOBOBJECT_BASIC_ACCOUNTING_INFORMATION state{};
                if (!QueryInformationJobObject(value, JobObjectBasicAccountingInformation,
                    &state, sizeof(state), nullptr) || state.ActiveProcesses == 0) break;
                Sleep(10);
            }
            CloseHandle(value);
        }
    } job;
    win(job.value != nullptr, "job_create");
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        | JOB_OBJECT_LIMIT_ACTIVE_PROCESS;
    limits.BasicLimitInformation.ActiveProcessLimit = 4;
    win(SetInformationJobObject(job.value, JobObjectExtendedLimitInformation,
        &limits, sizeof(limits)), "job_limits");
    JOBOBJECT_BASIC_UI_RESTRICTIONS ui{JOB_OBJECT_UILIMIT_ALL};
    win(SetInformationJobObject(job.value, JobObjectBasicUIRestrictions,
        &ui, sizeof(ui)), "job_ui_limits");
    ContainerAttributes attributes(sid, lpac);
    STARTUPINFOEXW start{};
    start.StartupInfo.cb = sizeof(start);
    start.StartupInfo.lpDesktop = desktop.data();
    start.lpAttributeList = attributes.list;
    Local text;
    win(ConvertSidToStringSidW(sid, reinterpret_cast<LPWSTR*>(&text.value)), "sid_format");
    // AppContainer startup resolves its profile through this explicit OS path.
    // Chromium's filtered target environment retains LOCALAPPDATA for this reason.
    wchar_t local[32768]{};
    const DWORD local_length = GetEnvironmentVariableW(L"LOCALAPPDATA", local, 32768);
    require(local_length > 0 && local_length < 32768
        && fs::path(local).is_absolute() && fs::is_directory(local), "bootstrap_local_appdata");
    std::wstring command = quote(executable.wstring()) + L" --worker "
        + (lpac ? L"lpac" : L"regular") + L" parent " + quote(root.wstring())
        + L" " + quote(static_cast<LPCWSTR>(text.value)) + L" " + quote(executable.wstring())
        + L" " + quote(local);
    auto environment = environment_block(root, local);
    PROCESS_INFORMATION process{};
    win(CreateProcessW(executable.c_str(), command.data(), nullptr, nullptr, FALSE,
        EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
        | DETACHED_PROCESS, environment.data(), (root / L"target").c_str(),
        &start.StartupInfo, &process), "container_create");
    Handle held(process.hProcess), thread(process.hThread);
    // Assignment failure must also destroy the still-suspended owned child.
    struct Suspended {
        HANDLE process;
        bool assigned = false;
        ~Suspended() {
            if (!assigned) {
                TerminateProcess(process, 1);
                WaitForSingleObject(process, 5000);
            }
        }
    } suspended{held.value};
    win(AssignProcessToJobObject(job.value, held.value), "job_assign");
    suspended.assigned = true;
    token(held.value, sid);
    require(ResumeThread(thread.value) != static_cast<DWORD>(-1), "worker_resume");
    const std::wstring mode = lpac ? L"lpac" : L"regular";
    const auto report = root / L"target" / (mode + L"-descendant.pid");
    wait_file(report, "descendant_report", held.value);
    const DWORD pid = descendant_pid(report);
    require(pid != process.dwProcessId, "distinct_descendant_pid");
    Handle descendant(OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, FALSE, pid));
    win(descendant.value != nullptr, "descendant_open");
    BOOL in_owned_job = FALSE;
    win(IsProcessInJob(descendant.value, job.value, &in_owned_job), "descendant_owned_job_query");
    require(in_owned_job, "descendant_owned_job");
    token(descendant.value, sid);
    // Only the parent can write this read-only-to-worker directory. The child
    // remains suspended until its exact token and owned job have been checked.
    publish(root / L"read" / (mode + L"-descendant-approved"), "synthetic fixture\n");
    wait_process(held.value);
    wait_process(descendant.value);
    JOBOBJECT_BASIC_ACCOUNTING_INFORMATION accounting{};
    // A signaled process handle does not establish quiescence of its job.
    // Observe the same owned job; never launch or repeat an effect here.
    for (int observation = 0; observation < 200; ++observation) {
        win(QueryInformationJobObject(job.value, JobObjectBasicAccountingInformation,
            &accounting, sizeof(accounting), nullptr), "job_accounting");
        if (accounting.ActiveProcesses == 0) break;
        Sleep(10);
    }
    std::cout << "{\"diagnostic\":\"owned_job_accounting\",\"total\":"
        << accounting.TotalProcesses << ",\"active\":" << accounting.ActiveProcesses
        << ",\"terminated\":" << accounting.TotalTerminatedProcesses << "}" << std::endl;
    require(accounting.TotalProcesses >= 2 && accounting.TotalProcesses <= 4
        && accounting.ActiveProcesses == 0,
        "actual_descendant_job_custody");
    for (const auto& role : {L"parent", L"child"}) {
        const auto label = std::wstring(lpac ? L"lpac" : L"regular") + L"-" + role;
        readable(root / L"target" / (label + L".written"));
    }
}
int parent() {
    wchar_t actions[8]{}, runner[16]{};
    require(GetEnvironmentVariableW(L"GITHUB_ACTIONS", actions, 8) == 4
        && std::wstring(actions) == L"true"
        && GetEnvironmentVariableW(L"RUNNER_OS", runner, 16) == 7
        && std::wstring(runner) == L"Windows", "disposable_ci_only");
    wchar_t temporary[32768]{};
    const DWORD temporary_length = GetEnvironmentVariableW(L"RUNNER_TEMP", temporary, 32768);
    require(temporary_length > 0 && temporary_length < 32768, "runner_temporary");
    GUID guid{};
    require(CoCreateGuid(&guid) == S_OK, "fixture_identifier");
    wchar_t identifier[40]{};
    require(StringFromGUID2(guid, identifier, 40) != 0, "fixture_identifier_format");
    std::wstring suffix(identifier);
    suffix = suffix.substr(1, suffix.size() - 2);
    Fixture fixture;
    fixture.root = fs::path(temporary) / (L"ai-stp-confinement-" + suffix);
    require(fs::create_directory(fixture.root), "new_fixture_directory");
    fixture.owned = true;
    Profile profile;
    profile.name = L"ai-stp-probe-" + suffix;
    const HRESULT result = CreateAppContainerProfile(profile.name.c_str(),
        L"ai-stp disposable CI", L"Owned confinement experiment", nullptr, 0, &profile.sid);
    require(result == S_OK, "new_profile", static_cast<DWORD>(result));
    profile.created = true;
    grant(fixture.root, profile.sid, FILE_TRAVERSE, NO_INHERITANCE);
    for (const auto& name : {L"read", L"target", L"outside", L"aap"})
        require(fs::create_directory(fixture.root / name), "new_fixture_child");
    grant(fixture.root / L"read", profile.sid, FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
        SUB_CONTAINERS_AND_OBJECTS_INHERIT);
    grant(fixture.root / L"target", profile.sid, FILE_ALL_ACCESS,
        SUB_CONTAINERS_AND_OBJECTS_INHERIT);
    low_integrity(fixture.root / L"target");
    Local all_packages;
    win(ConvertStringSidToSidW(L"S-1-15-2-1", &all_packages.value), "aap_sid_parse");
    grant(fixture.root / L"aap", all_packages.value, FILE_GENERIC_READ | FILE_GENERIC_EXECUTE,
        SUB_CONTAINERS_AND_OBJECTS_INHERIT);
    for (const auto& name : {L"read", L"outside", L"aap"})
        write(fixture.root / name / L"canary", "synthetic fixture\n");
    write(fixture.root / L"outside" / L"credentials", "synthetic fixture\n");
    wchar_t source[32768]{};
    const DWORD length = GetModuleFileNameW(nullptr, source, 32768);
    require(length > 0 && length < 32768, "probe_executable");
    const auto executable = fixture.root / L"read" / L"probe.exe";
    require(fs::copy_file(source, executable), "probe_copy");
    win(SetEnvironmentVariableW(L"AI_STP_PROBE_PARENT_SECRET", L"synthetic fixture"),
        "parent_environment_canary");
    for (const auto& name : {L"read", L"outside", L"aap"})
        readable(fixture.root / name / L"canary");
    for (const bool lpac : {false, true}) {
        std::cout << "{\"stage\":\"" << (lpac ? "lpac_execution" : "regular_appcontainer_execution")
            << "\"}" << std::endl;
        PrivateDesktop desktop(profile.sid, L"ai-stp-" + suffix + (lpac ? L"-lpac" : L"-regular"));
        run(executable, fixture.root, profile.sid, lpac, desktop.full_name);
        desktop.close();
    }
    readable(fixture.root / L"outside" / L"canary");
    readable(fixture.root / L"outside" / L"credentials");
    win(SetEnvironmentVariableW(L"AI_STP_PROBE_PARENT_SECRET", nullptr),
        "parent_environment_cleanup");
    profile.close();
    fixture.close();
    std::cout << "{\"windows_confinement_experiment\":\"passed\","
        "\"phase\":\"token_filesystem_descendants\",\"executed_workers\":4,"
        "\"regular_aap_positive_control\":true,\"lpac_aap_denied\":true,"
        "\"own_target_read_write\":true,\"outside_read_write_denied\":true,"
        "\"synthetic_credentials_denied\":true,\"parent_environment_filtered\":true,"
        "\"descendants_in_owned_job\":true,\"owned_cleanup\":true,"
        "\"network_qualified\":false,\"broker_qualified\":false,"
        "\"provider_runtime_enabled\":false}" << std::endl;
    return 0;
}
int wmain(int argc, wchar_t** argv) {
    try {
        if (argc > 1 && std::wstring(argv[1]) == L"--worker") return worker(argc, argv);
        require(argc == 1, "parent_arguments");
        return parent();
    } catch (const Failure& failure) {
        // Stages are literals and codes are native numeric categories only.
        std::cout << "{\"stage\":\"" << failure.stage << "\",\"native_code\":"
            << failure.code << "}" << std::endl;
        if (argc == 8 && std::wstring(argv[1]) == L"--worker") {
            try {
                require((std::wstring(argv[2]) == L"lpac" || std::wstring(argv[2]) == L"regular")
                    && (std::wstring(argv[3]) == L"parent" || std::wstring(argv[3]) == L"child"),
                    "worker_arguments");
                PROCESS_MITIGATION_CHILD_PROCESS_POLICY policy{};
                const bool policy_known = GetProcessMitigationPolicy(GetCurrentProcess(),
                    ProcessChildProcessPolicy, &policy, sizeof(policy)) != FALSE;
                wchar_t local[32768]{};
                const DWORD length = GetEnvironmentVariableW(L"LOCALAPPDATA", local, 32768);
                const bool bootstrap_matches = length > 0 && length < 32768
                    && _wcsicmp(local, argv[7]) == 0;
                publish(fs::path(argv[4]) / L"target"
                    / (std::wstring(argv[2]) + L"-" + argv[3] + L".failure"),
                    std::to_string(worker_stage_code(failure.stage)) + " "
                    + std::to_string(failure.code) + " " + (policy_known ? "1" : "0")
                    + " " + (policy_known && policy.NoChildProcessCreation ? "1" : "0")
                    + " " + (bootstrap_matches ? "1" : "0") + "\n");
            } catch (...) { /* The original failure remains authoritative. */ }
            return static_cast<int>(worker_stage_code(failure.stage));
        }
        return 1;
    } catch (...) {
        std::cout << "{\"stage\":\"unexpected_fixture_failure\"}" << std::endl;
        return 1;
    }
}
