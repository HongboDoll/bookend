#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import resource
import bookend.core.cython_utils._rnaseq_utils as ru
from bookend.core.cython_utils._pq import IndexMinPQ
if __name__ == '__main__':
    sys.path.append('../../bookend')
    from argument_parsers import combine_parser as parser

class ELRcombiner:
    def __init__(self, args):
        """Leaves together ELR files in sort order"""
        self.strand_sort_values = {'+':-1, '.':0, '-':1}
        self.strand_reverse_values = {-1:'+', 0:'.', 1:'-'}
        self.input = args['INPUT']
        self.output = args['OUTPUT']
        self.temp = args['TEMPDIR']
        if self.output == 'stdout':
            self.output_file = 'stdout'
        else:
            self.output_file = open(self.output, 'w')
        
        self.linecount = 0
        self.readcount = 0
        self.number_of_files = len(self.input)
        self.PQ = IndexMinPQ(self.number_of_files)
    
    def get_header(self, file):
        """From an open connection to an ELR file, 
        extract the header information and store it as
        a master lookup table for output chrom and source.
        Returns the first line without a header and keeps
        the file open at the existing buffer position."""
        header = {'chrom':{}, 'source':{}}
        file.seek(0)
        line = file.readline().rstrip()
        if len(line) == 0:
            return header, line
        
        while line[0] == '#':
            header_line = line.split(' ')
            num, char = header_line[-2:]
            if header_line[0] == '#S':
                header['source'][num] = char
            elif header_line[0] == '#C':
                header['chrom'][num] = char
            
            line = file.readline().rstrip()
        
        return header, line

    def read_to_sortable_tuple(self, line, index):
        """Convert an ELR line into an RNAseqMapping object
        with shared chrom and source indices."""
        split_line = line.split('\t')
        # Swap index for the merged index value
        chrom = int(self.dataset.chrom_dict[self.file_headers[index]['chrom'][split_line[0]]])
        start = int(split_line[1])
        length = int(split_line[2])
        strand = self.strand_sort_values[split_line[3]]
        elcigar = split_line[4]
        source = int(self.dataset.source_dict[self.file_headers[index]['source'][split_line[5]]])
        weight = -float(split_line[6])
        return (chrom, start, length, strand, elcigar, source, weight)

    def sortable_tuple_to_read(self, sortable_tuple):
        l = list(sortable_tuple)
        l[3] = self.strand_reverse_values[l[3]]    
        l[6] = -l[6]
        return '\t'.join([str(i) for i in l])
    
    def output_line(self, line):
        """Takes a list of bed lines and writes
        them to the output stream.
        """
        if self.output_file == 'stdout':
            print(line)
        else:
            self.output_file.write('{}\n'.format(line.rstrip()))
    
    def run(self):
        if self.output != 'stdout':
            self.display_options()
        
        self.combine_files()
        if self.output != 'stdout':
            self.display_summary()
    
    def combine_files(self):
        if self.input:
            if not all([i[-3:].lower()=='elr' for i in self.input]):
                print("\nERROR: all input files must be ELR format.")
                sys.exit(1)
        
            filenames = self.input
            #TODO: Check open file resource limits!
            files = [open(f) for f in filenames]
        else:
            print("\nERROR: requires ELR file as input.")
            sys.exit(1)
        
        self.file_headers = ['']*self.number_of_files
        current_lines = ['']*self.number_of_files
        for i in range(self.number_of_files):
            self.file_headers[i], current_lines[i] = self.get_header(files[i])
            if i == 0: # Store the first chroms list
                chrom_num = len(self.file_headers[i]['chrom'])
                self.chroms = [self.file_headers[i]['chrom'][str(i)] for i in range(chrom_num)]
            else:
                if self.file_headers[i]['chrom'] != self.file_headers[0]['chrom']:
                    print("ERROR: chromosome index does not match across input files!")
                    print("Check that the same genome was used for all alignments.")
                    sys.exit(1)
        
        set_of_sources = set()
        for h in self.file_headers:
            set_of_sources.update(h['source'].values())
        
        self.merged_sources = sorted(list(set_of_sources))
        self.dataset = ru.RNAseqDataset(chrom_array=self.chroms, source_array=self.merged_sources)
        # Initialize the priority queue with one ELR read object from each file
        
        finished_files = 0
        for index, line in enumerate(current_lines):
            if line: # Populate the queue with the first line
                item = self.read_to_sortable_tuple(line, index)
                self.PQ.insert(index, item)
            else: # The file was empty
                files[index].close()
                finished_files += 1
        
        for h in self.dataset.dump_header():
            self.output_line(h)
        
        while finished_files < self.number_of_files: # Keep going until every line of every file is processed
            index, item = self.PQ.pop(True)
            self.output_line(self.sortable_tuple_to_read(item))
            next_line = files[index].readline().rstrip()
            if next_line:
                next_item = self.read_to_sortable_tuple(next_line, index)
                self.PQ.insert(index, next_item)
            else: # No more lines in this file
                files[index].close()
                finished_files += 1
    
    def display_options(self):
        """Returns a string describing all input args"""
        options_string = "\n/| bookend bed-to-elr |\\\n¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯\n"
        options_string += "  Input file:     {}\n".format(self.input)
        options_string += "  Output file:    {}\n".format(self.output)
        options_string += "  Temp directory: {}\n".format(self.temp)
        return options_string
    
    def display_summary(self):
        summary_string = ''
        summary_string += 'Wrote {} lines ({} total reads) from {} files.\n'.format(self.linecount, round(self.readcount,2), self.number_of_files)
        return summary_string

####################
# PARSE INPUT FILE #
####################
if __name__ == '__main__':
    args = vars(parser.parse_args())
    obj = ELRcombiner(args)
    sys.exit(obj.run())
