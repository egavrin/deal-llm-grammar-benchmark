#include "src/unicode.h"
#include "src/llama-grammar.h"

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

static std::string read_file(const char * path) {
    std::ifstream input(path);
    std::stringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

static bool validate(llama_grammar * grammar, const std::string & input) {
    auto & stacks = llama_grammar_get_stacks(grammar);
    for (const auto codepoint : unicode_cpts_from_utf8(input)) {
        llama_grammar_accept(grammar, codepoint);
        if (stacks.empty()) {
            return false;
        }
    }
    for (const auto & stack : stacks) {
        if (stack.empty()) {
            return true;
        }
    }
    return false;
}

int main(int argc, char ** argv) {
    if (argc < 4) {
        std::cerr << "usage: gbnf-throughput GRAMMAR ROUNDS INPUT...\n";
        return 2;
    }
    const std::string grammar_text = read_file(argv[1]);
    const int rounds = std::atoi(argv[2]);
    std::vector<std::string> inputs;
    size_t bytes_per_round = 0;
    for (int index = 3; index < argc; ++index) {
        inputs.push_back(read_file(argv[index]));
        bytes_per_round += inputs.back().size();
    }
    llama_grammar * base = llama_grammar_init_impl(nullptr, grammar_text.c_str(), "root", false, nullptr, 0, nullptr, 0);
    if (base == nullptr) {
        std::cerr << "grammar initialization failed\n";
        return 3;
    }
    int failures = 0;
    const auto started = std::chrono::steady_clock::now();
    for (int round = 0; round < rounds; ++round) {
        for (const auto & input : inputs) {
            llama_grammar * instance = llama_grammar_clone_impl(*base);
            failures += !validate(instance, input);
            llama_grammar_free_impl(instance);
        }
    }
    const auto elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
    const size_t programs = static_cast<size_t>(rounds) * inputs.size();
    const size_t bytes = static_cast<size_t>(rounds) * bytes_per_round;
    std::cout << "{\"programs\":" << programs
              << ",\"failures\":" << failures
              << ",\"seconds\":" << elapsed
              << ",\"programs_per_second\":" << programs / elapsed
              << ",\"mib_per_second\":" << (bytes / 1048576.0) / elapsed
              << "}\n";
    llama_grammar_free_impl(base);
    return failures == 0 ? 0 : 1;
}
