// Simplest possible test — just write a file to disk.
// If this file gets created, we know -s is working.
var f = new File("F:/Adobe_FDE Take-Home/yosuki-pipeline/output/projects/jsx_ran.txt");
f.open("w");
f.writeln("JSX ran at: " + new Date().toString());
f.close();
