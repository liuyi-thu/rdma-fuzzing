# Makefile to compile all *.c files into build/ with -g -libverbs

# Compiler and flags
CC = gcc
CFLAGS = -g -libverbs

# Find all .c files and corresponding executable names
SRCS := $(wildcard *.c)
BINS := $(patsubst %.c, build/%, $(SRCS))

# Default target
all: $(BINS)

# Ensure build directory exists
build:
	mkdir -p build

# Rule to compile each .c file to build/<binary>
build/%: %.c | build
	$(CC) $< -o $@ $(CFLAGS)

# Clean target
clean:
	rm -rf build

.PHONY: all clean
