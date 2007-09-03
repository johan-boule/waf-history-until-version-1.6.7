module abc.
def.	gh;

import std.stdio;       // for writefln()
import std .  // system2;
system  ;
static import std.date, std.thread /+ /+ +/ , std.io +/ ;
import std.boxer, uhf = std.date, io = std.stdio : foo = writef, read  ;

int main(string[] args)   // string is a type alias for const(char)[]
{
    // Declare an associative array with string keys and
    // arrays of strings as data
    char[][] [char[]] container;
 
    // Add some people to the container and let them carry some items
    container["Anya"] ~= "scarf";
    container["Dimitri"] ~= "tickets";
    container["Anya"] ~= "puppy";

    // Iterate over all the persons in the container
    foreach (char[] person, char[][] items; container)
        display_item_count(person, items);
    return 0;
}
 
void display_item_count(char[] person, char[][] items)
{
    writefln(person, " is carrying ", items.length, " items.");
}
