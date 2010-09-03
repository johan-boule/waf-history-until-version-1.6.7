
#if A
  #if B
    #if C
      #include "a.h"
    #else
      #include "b.h"
    #endif
  #else
    #if C
      #include "c.h"
    #else
      #include "d.h"
    #endif
  #endif
#elif B
  #if C
     #include <e.h>
  #else
     #include "f.h"
  #endif
#elif C
  #include "g.h"
#else
  #include "h.h"
#endif


/*
#include "a.h"
*/
//#include "a.h"

int main() {
	return 0;
}
