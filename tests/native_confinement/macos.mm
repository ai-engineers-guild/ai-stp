// Disposable CI feasibility experiment, not a provider runtime or product grant.
// developer.apple.com/documentation/security/accessing-files-from-the-macos-app-sandbox
#import <Foundation/Foundation.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <csignal>
#include <cstring>
#include <fcntl.h>
#include <iostream>
#include <poll.h>
#include <spawn.h>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

struct Failure { const char* stage; int code; };
void require(bool value, const char* stage, int code = 0) {
    if (!value) throw Failure{stage, code};
}
struct Descriptor {
    int value = -1;
    explicit Descriptor(int fd = -1) : value(fd) {}
    ~Descriptor() { if (value >= 0) close(value); }
    void reset() { if (value >= 0) close(value); value = -1; }
    Descriptor(const Descriptor&) = delete;
    Descriptor& operator=(const Descriptor&) = delete;
};
const char* bytes(NSString* value) {
    require([value isKindOfClass:[NSString class]] && value.length < 32768,
        "path_shape");
    const char* result = value.UTF8String;
    require(result && std::strlen(result) == [value lengthOfBytesUsingEncoding:NSUTF8StringEncoding],
        "path_encoding");
    return result;
}
NSString* joined(NSString* root, NSString* leaf) {
    return [root stringByAppendingPathComponent:leaf];
}
void readable(NSString* path) {
    Descriptor file(open(bytes(path), O_RDONLY | O_NOFOLLOW | O_CLOEXEC));
    require(file.value >= 0, "positive_read_open", errno);
    char data[64]{};
    const ssize_t count = read(file.value, data, sizeof(data));
    require(count == 18 && std::string(data, 18) == "synthetic fixture\n",
        "positive_read_bytes", errno);
}
void refused(NSString* path, int access) {
    Descriptor file(open(bytes(path), access | O_NOFOLLOW | O_CLOEXEC));
    const int original = errno;
    require(file.value == -1 && (original == EPERM || original == EACCES),
        "outside_or_ungranted_access", original);
}
void write_new(NSString* path) {
    Descriptor file(open(bytes(path), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600));
    require(file.value >= 0, "owned_write_open", errno);
    constexpr char value[] = "synthetic fixture\n";
    require(write(file.value, value, sizeof(value) - 1) == static_cast<ssize_t>(sizeof(value) - 1),
        "owned_write", errno);
}
NSData* input() {
    NSMutableData* data = [NSMutableData data];
    char block[1024];
    for (;;) {
        const ssize_t count = read(STDIN_FILENO, block, sizeof(block));
        if (count < 0 && errno == EINTR) continue;
        require(count >= 0, "input_read", errno);
        if (count == 0) return data;
        require(data.length + static_cast<size_t>(count) <= 4096, "input_bound");
        [data appendBytes:block length:static_cast<NSUInteger>(count)];
    }
}
NSDictionary* decode(NSData* data) {
    NSError* error = nil;
    id value = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
    require([value isKindOfClass:[NSDictionary class]] && !error, "input_json");
    return value;
}
std::string launch(NSString* executable, const char* role, NSData* data, bool group) {
    require(data.length > 0 && data.length <= 4096, "launch_input_bound");
    int incoming[2], outgoing[2];
    require(pipe(incoming) == 0, "stdin_pipe", errno);
    Descriptor input_read(incoming[0]), input_write(incoming[1]);
    require(pipe(outgoing) == 0, "stdout_pipe", errno);
    Descriptor output_read(outgoing[0]), output_write(outgoing[1]);
    posix_spawn_file_actions_t actions;
    require(posix_spawn_file_actions_init(&actions) == 0, "spawn_actions");
    struct Actions {
        posix_spawn_file_actions_t* value;
        ~Actions() { posix_spawn_file_actions_destroy(value); }
    } held_actions{&actions};
    require(posix_spawn_file_actions_adddup2(&actions, input_read.value, STDIN_FILENO) == 0
        && posix_spawn_file_actions_adddup2(&actions, output_write.value, STDOUT_FILENO) == 0
        && posix_spawn_file_actions_adddup2(&actions, output_write.value, STDERR_FILENO) == 0,
        "spawn_stdio");
    for (int descriptor : {input_read.value, input_write.value, output_read.value, output_write.value}) {
        require(descriptor > STDERR_FILENO
            && posix_spawn_file_actions_addclose(&actions, descriptor) == 0,
            "spawn_close_owned_descriptors");
    }
    posix_spawnattr_t attributes;
    require(posix_spawnattr_init(&attributes) == 0, "spawn_attributes");
    struct Attributes {
        posix_spawnattr_t* value;
        ~Attributes() { posix_spawnattr_destroy(value); }
    } held_attributes{&attributes};
    short flags = POSIX_SPAWN_CLOEXEC_DEFAULT;
    if (group) {
        flags |= POSIX_SPAWN_SETPGROUP;
        require(posix_spawnattr_setpgroup(&attributes, 0) == 0, "spawn_group");
    }
    require(posix_spawnattr_setflags(&attributes, flags) == 0, "spawn_flags");
    char path[] = "PATH=/usr/bin:/bin", locale[] = "LC_ALL=C";
    char* environment[] = {path, locale, nullptr};
    char* arguments[] = {const_cast<char*>(bytes(executable)), const_cast<char*>(role), nullptr};
    pid_t pid = -1;
    const int created = posix_spawn(&pid, bytes(executable), &actions, &attributes,
        arguments, environment);
    require(created == 0 && pid > 0, "actual_worker_spawn", created);
    struct Child {
        pid_t pid;
        bool group;
        ~Child() {
            kill(group ? -pid : pid, SIGKILL);
            while (waitpid(pid, nullptr, 0) < 0 && errno == EINTR) {}
        }
    } child{pid, group};
    input_read.reset();
    output_write.reset();
    require(fcntl(input_write.value, F_SETFL, O_NONBLOCK) == 0, "input_nonblocking", errno);
    require(fcntl(output_read.value, F_SETFL, O_NONBLOCK) == 0, "output_nonblocking", errno);
    std::string output;
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(group ? 30 : 15);
    siginfo_t status{};
    bool exited = false, ended = false;
    size_t sent = 0;
    while (!exited || !ended) {
        require(std::chrono::steady_clock::now() < deadline, "worker_timeout");
        if (input_write.value >= 0) {
            const ssize_t count = write(input_write.value,
                static_cast<const char*>(data.bytes) + sent, data.length - sent);
            if (count > 0) sent += static_cast<size_t>(count);
            else require(count < 0 && (errno == EAGAIN || errno == EINTR), "input_write", errno);
            if (sent == data.length) input_write.reset();
        }
        char buffer[1024];
        const ssize_t count = read(output_read.value, buffer, sizeof(buffer));
        if (count > 0) {
            require(output.size() + static_cast<size_t>(count) <= 4096, "output_bound");
            output.append(buffer, static_cast<size_t>(count));
        } else if (count == 0) ended = true;
        else require(errno == EAGAIN || errno == EINTR, "output_read", errno);
        if (!exited) {
            const int observed = waitid(P_PID, static_cast<id_t>(pid), &status,
                WNOHANG | WNOWAIT | WEXITED);
            require(observed == 0 || errno == EINTR, "worker_wait", errno);
            exited = observed == 0 && status.si_pid == pid;
        }
        if (!exited || !ended) {
            pollfd wait{output_read.value, POLLIN, 0};
            require(poll(ended ? nullptr : &wait, ended ? 0 : 1, 10) >= 0 || errno == EINTR,
                "worker_poll", errno);
        }
    }
    if (status.si_code != CLD_EXITED || status.si_status != 0) {
        // Workers emit literal failure stages and numeric codes, never descriptions.
        // Forward only these bounded fields, including nested worker observations.
        std::istringstream lines(output);
        for (std::string line; std::getline(lines, line);) {
            if (line.size() > 512) continue;
            NSError* error = nil;
            NSData* encoded = [NSData dataWithBytes:line.data() length:line.size()];
            id record = [NSJSONSerialization JSONObjectWithData:encoded options:0 error:&error];
            if (error || ![record isKindOfClass:[NSDictionary class]]) continue;
            NSString* stage = record[@"stage"];
            NSNumber* code = record[@"native_code"];
            if (![stage isKindOfClass:[NSString class]] || stage.length == 0 || stage.length > 64
                || ![code isKindOfClass:[NSNumber class]]) continue;
            const std::string value(bytes(stage));
            if (!std::all_of(value.begin(), value.end(), [](char c) {
                return (c >= 'a' && c <= 'z') || c == '_';
            })) continue;
            std::cout << "{\"stage\":\"" << value << "\",\"native_code\":"
                << code.longLongValue << "}" << std::endl;
        }
        throw Failure{"worker_exit", status.si_status};
    }
    require(sent == data.length, "input_complete");
    // WNOWAIT keeps the primary PID reserved until owned-group cleanup/reaping.
    return output;
}
NSDictionary* worker(NSString* role) {
    NSData* data = input();
    NSDictionary* request = decode(data);
    require(request.count == 3, "request_shape");
    NSString* root = request[@"root"];
    NSString* child = request[@"child"];
    require([root isKindOfClass:[NSString class]] && root.isAbsolutePath
        && [child isKindOfClass:[NSString class]] && child.isAbsolutePath, "worker_paths");
    require(getenv("AI_STP_PROBE_PARENT_SECRET") == nullptr, "environment_secret_absent");
    NSString* target = joined(root, @"target");
    refused(joined(target, @"canary"), O_RDONLY);
    NSError* error = nil;
    require([request[@"bookmark"] isKindOfClass:[NSString class]], "bookmark_encoding");
    NSData* bookmark = [[NSData alloc] initWithBase64EncodedString:request[@"bookmark"] options:0];
    require(bookmark.length > 0 && bookmark.length < 3072, "bookmark_bound");
    BOOL stale = NO;
    NSURL* location = [NSURL URLByResolvingBookmarkData:bookmark options:0 relativeToURL:nil
        bookmarkDataIsStale:&stale error:&error];
    require(location != nil, "implicit_bookmark_location", static_cast<int>(error.code));
    require(error == nil, "implicit_bookmark_error", static_cast<int>(error.code));
    require(!stale, "implicit_bookmark_stale");
    require([location.path isEqualToString:target], "implicit_bookmark_target");
    struct Scope {
        NSURL* value;
        ~Scope() { [value stopAccessingSecurityScopedResource]; }
    } scope{location};
    readable(joined(target, @"canary"));
    NSString* written = joined(target, [role stringByAppendingString:@".written"]);
    write_new(written);
    readable(written);
    for (NSString* leaf in @[@"outside/canary", @"outside/credentials"]) {
        refused(joined(root, leaf), O_RDONLY);
        refused(joined(root, leaf), O_WRONLY);
    }
    if ([role isEqualToString:@"worker"]) {
        std::string result = launch(child, "child", data, false);
        NSDictionary* proof = decode([NSData dataWithBytes:result.data() length:result.size()]);
        require([proof[@"role"] isEqual:@"child"] && [proof[@"pid"] intValue] > 0
            && [proof[@"pid"] intValue] != getpid() && [proof[@"io"] isEqual:@YES],
            "actual_descendant_proof");
        readable(joined(target, @"child.written"));
    }
    return @{@"role":role, @"pid":@(getpid()), @"io":@YES};
}
int main(int argc, char** argv) {
    @autoreleasepool {
        try {
            require(signal(SIGPIPE, SIG_IGN) != SIG_ERR, "pipe_signal", errno);
            require(argc == 2 || argc == 5, "arguments");
            NSString* role = [NSString stringWithUTF8String:argv[1]];
            NSDictionary* proof = nil;
            if (argc == 2) {
                require([role isEqual:@"worker"] || [role isEqual:@"child"], "worker_role");
                proof = worker(role);
            } else {
                require([role isEqual:@"controller"] && getenv("GITHUB_ACTIONS")
                    && std::strcmp(getenv("GITHUB_ACTIONS"), "true") == 0,
                    "disposable_ci_only");
                NSString* root = [NSString stringWithUTF8String:argv[2]];
                NSString* executable = [NSString stringWithUTF8String:argv[3]];
                NSString* child = [NSString stringWithUTF8String:argv[4]];
                require(root.isAbsolutePath && executable.isAbsolutePath && child.isAbsolutePath,
                    "controller_paths");
                for (NSString* leaf in @[@"target/canary", @"outside/canary", @"outside/credentials"])
                    readable(joined(root, leaf));
                NSError* error = nil;
                NSURL* target = [NSURL fileURLWithPath:joined(root, @"target") isDirectory:YES];
                NSData* bookmark = [target bookmarkDataWithOptions:0 includingResourceValuesForKeys:nil
                    relativeToURL:nil error:&error];
                require(bookmark.length > 0 && bookmark.length < 3072 && !error,
                    "implicit_bookmark_creation", static_cast<int>(error.code));
                NSDictionary* request = @{@"root":root, @"child":child,
                    @"bookmark":[bookmark base64EncodedStringWithOptions:0]};
                NSData* input = [NSJSONSerialization dataWithJSONObject:request options:0 error:&error];
                require(input && !error, "controller_input");
                require(setenv("AI_STP_PROBE_PARENT_SECRET", "synthetic fixture", 1) == 0,
                    "parent_environment", errno);
                std::string result = launch(executable, "worker", input, true);
                NSDictionary* observed = decode([NSData dataWithBytes:result.data() length:result.size()]);
                require([observed[@"role"] isEqual:@"worker"] && [observed[@"io"] isEqual:@YES],
                    "actual_worker_proof");
                for (NSString* leaf in @[@"target/worker.written", @"target/child.written",
                    @"outside/canary", @"outside/credentials"]) readable(joined(root, leaf));
                proof = @{@"macos_confinement_experiment":@"passed", @"executed_workers":@2,
                    @"implicit_bookmark_transfer":@YES, @"outside_and_credentials_denied":@YES,
                    @"ungranted_target_denied":@YES, @"descendant_executed":@YES,
                    @"environment_filtered":@YES, @"network_qualified":@NO,
                    @"broker_qualified":@NO, @"provider_runtime_enabled":@NO,
                    @"release_signing_qualified":@NO, @"packaged_desktop_qualified":@NO};
            }
            NSError* error = nil;
            NSData* encoded = [NSJSONSerialization dataWithJSONObject:proof options:0 error:&error];
            require(encoded && !error, "proof_encoding");
            std::cout.write(static_cast<const char*>(encoded.bytes), encoded.length);
            std::cout << std::endl;
            return 0;
        } catch (const Failure& failure) {
            std::cout << "{\"stage\":\"" << failure.stage << "\",\"native_code\":"
                << failure.code << "}" << std::endl;
            return 1;
        }
    }
}
